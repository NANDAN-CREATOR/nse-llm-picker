"""End-to-end test on synthetic data: pick -> evaluate -> scorecard -> Excel."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from picker import config as C
from picker.evaluate import evaluate, scorecard
from picker.features import compute_features, quant_score
from picker.llm import NewsScorer
from picker.pipeline import format_pick, run_pick
from picker.report import build_report
from picker.store import Store
from picker.tradingdays import next_trading_day

ASOF = date(2026, 11, 23)  # Monday close
NOW = datetime(2026, 11, 23, 22, 55, tzinfo=C.IST)


def make_df(seed, drift=0.0005, end=ASOF, n=520):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.012, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.004, n)))
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": rng.integers(1e6, 2e6, n)}, index=idx)


UNIVERSE = [(f"S{i}", f"Company {i}") for i in range(12)]
HIST = {s: make_df(i, drift=0.0008 * (i - 6) / 6 + 0.0003) for i, (s, _) in enumerate(UNIVERSE)}


def news_fn(name):
    if name == "Company 11":
        return [{"title": "Company 11 profit jumps, order win announced", "source": "x", "published": ""}]
    return [{"title": f"{name} shares fall on probe", "source": "x", "published": ""}]


def test_holiday_is_skipped():
    # 24 Nov 2026 is a market holiday (Guru Nanak Jayanti) -> next session is Wed 25 Nov
    assert next_trading_day(date(2026, 11, 23)) == date(2026, 11, 25)
    assert next_trading_day(date(2026, 11, 27)) == date(2026, 11, 30)  # Fri -> Mon


def test_features_and_score_bounds():
    f = compute_features(HIST["S3"], date(2026, 11, 25))
    assert f and 0 <= f["rsi14"] <= 100 and f["atr_pct"] > 0
    s, parts = quant_score(f)
    assert -1 <= s <= 1 and set(parts) == {"momentum", "trend", "rsi", "volume", "seasonal"}


def test_pick_then_evaluate(tmp_path):
    store = Store(tmp_path / "t.db")
    rows = run_pick(UNIVERSE, now=NOW, history_fn=lambda syms: HIST, news_fn=news_fn,
                    scorer=NewsScorer(use_llm=False), store=store, shortlist=12)
    assert len(rows) == C.TOP_LOGGED and rows[0]["rank"] == 1
    assert rows[0]["target_date"] == "2026-11-25"
    assert rows[0]["symbol"] == "S11"  # strongest news + positive headlines
    assert rows[0]["target_price"] > rows[0]["ref_close"] > rows[0]["stop_price"]
    assert "PICK for session 2026-11-25" in format_pick(rows)

    # re-running before the session replaces pending rows, no duplicates
    run_pick(UNIVERSE, now=NOW, history_fn=lambda syms: HIST, news_fn=news_fn,
             scorer=NewsScorer(use_llm=False), store=store, shortlist=12)
    assert len(store.frame()) == C.TOP_LOGGED

    # too early: session not finished, nothing evaluated
    assert evaluate(store, now=datetime(2026, 11, 25, 12, 0, tzinfo=C.IST), ohlc_fn=lambda *a: None) == 0

    # reality: pick closes +1.2%, others -0.5%; benchmark +0.4%
    ref = {r["symbol"]: r["ref_close"] for r in store.frame().to_dict("records")}

    def ohlc_fn(sym, exch, start, end):
        if sym == C.BENCHMARK:
            idx = pd.to_datetime(["2026-11-23", "2026-11-25"])
            return pd.DataFrame({"Open": 100., "High": 101., "Low": 99., "Close": [100., 100.4], "Volume": 1}, index=idx)
        r = ref[sym]
        chg = 0.012 if sym == "S11" else -0.005
        idx = pd.to_datetime(["2026-11-25"])
        return pd.DataFrame({"Open": r * 1.002, "High": r * (1 + abs(chg) + 0.01),
                             "Low": r * (1 - 0.001), "Close": r * (1 + chg), "Volume": 1}, index=idx)

    n = evaluate(store, now=datetime(2026, 11, 25, 22, 0, tzinfo=C.IST), ohlc_fn=ohlc_fn)
    assert n == C.TOP_LOGGED

    df = store.frame()
    pick = df[df["rank"] == 1].iloc[0]
    assert pick["status"] == "evaluated"
    assert pick["act_ret_pct"] == pytest.approx(1.2, abs=0.01)
    assert pick["alpha_pct"] == pytest.approx(0.8, abs=0.01)
    assert pick["error_pp"] == pytest.approx(pick["act_ret_pct"] - pick["exp_ret_pct"], abs=0.002)
    assert pick["dir_hit"] == 1 and pick["target_hit"] == 1 and pick["stop_hit"] == 0

    sc = scorecard(df)
    assert sc["pick"]["n"] == 1 and sc["pick"]["direction_hit_rate"] == 1.0
    shadow = df[df["rank"] > 1]
    assert sc["shadow"]["n"] == C.TOP_LOGGED - 1
    # every shadow stock fell 0.5%: a hit only where the expectation was also negative
    assert sc["shadow"]["direction_hit_rate"] == pytest.approx((shadow["exp_ret_pct"] < 0).mean())

    # evaluated rows are frozen: re-running pick for the same session must not overwrite them
    run_pick(UNIVERSE, now=NOW, history_fn=lambda syms: HIST, news_fn=news_fn,
             scorer=NewsScorer(use_llm=False), store=store, shortlist=12)
    assert (store.frame()["status"] == "evaluated").all()

    # Excel report has the expected sheets and live formulas
    out = build_report(store, tmp_path / "tracker.xlsx")
    wb = load_workbook(out)
    assert wb.sheetnames == ["Manual", "Scorecard", "Predictions"]
    assert str(wb["Scorecard"]["B3"].value).startswith("=IFERROR(COUNTIFS")
    assert wb["Predictions"].max_row == 1 + C.TOP_LOGGED


def test_refuses_after_session_open(tmp_path):
    late = datetime(2026, 11, 25, 9, 30, tzinfo=C.IST)
    with pytest.raises(RuntimeError, match="already opened"):
        run_pick(UNIVERSE, now=late, history_fn=lambda s: HIST, news_fn=news_fn,
                 scorer=NewsScorer(use_llm=False), store=Store(tmp_path / "x.db"))


def test_export_latest(tmp_path):
    from picker.export import build_latest
    store = Store(tmp_path / "e.db")
    run_pick(UNIVERSE, now=NOW, history_fn=lambda s: HIST, news_fn=news_fn,
             scorer=NewsScorer(use_llm=False), store=store, shortlist=12)
    out = build_latest(store, NOW)
    assert out["target_date"] == "2026-11-25" and len(out["picks"]) == C.TOP_LOGGED
    assert out["picks"][0]["rank"] == 1 and out["history"] == []
    import json; json.dumps(out)  # must be serialisable
