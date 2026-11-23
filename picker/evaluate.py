"""After the close: fill in what actually happened and measure the gap."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from . import config as C
from .store import Store


def _bar(df: pd.DataFrame, d: date):
    ts = pd.Timestamp(d)
    return df.loc[ts] if ts in df.index else None


def evaluate(store: Store, *, now: datetime, ohlc_fn) -> int:
    """ohlc_fn(symbol, exchange, start, end) -> daily OHLC frame. Returns rows evaluated."""
    done = 0
    for row in store.pending():
        target = date.fromisoformat(row["target_date"])
        if target > now.date() or (target == now.date() and now.time() < C.DATA_READY):
            continue  # session not finished yet
        asof = date.fromisoformat(row["asof_date"])
        df = ohlc_fn(row["symbol"], row["exchange"], target - timedelta(days=3), target + timedelta(days=1))
        bar = None if df is None or df.empty else _bar(df, target)
        if bar is None:
            if (now.date() - target).days > 4:
                store.update(row["id"], status="no_session", evaluated_at=now.isoformat())
            continue

        ref = row["ref_close"]
        o, h, l, c = (float(bar[k]) for k in ("Open", "High", "Low", "Close"))
        act = (c / ref - 1) * 100
        exp = row["exp_ret_pct"]

        bench = None
        try:
            bdf = ohlc_fn(C.BENCHMARK, row["exchange"], asof - timedelta(days=3), target + timedelta(days=1))
            b0, b1 = _bar(bdf, asof), _bar(bdf, target)
            if b0 is not None and b1 is not None:
                bench = (float(b1["Close"]) / float(b0["Close"]) - 1) * 100
        except Exception as e:
            print(f"[eval] benchmark unavailable: {e}")

        store.update(
            row["id"], status="evaluated", act_open=round(o, 2), act_high=round(h, 2),
            act_low=round(l, 2), act_close=round(c, 2), act_ret_pct=round(act, 3),
            gap_pct=round((o / ref - 1) * 100, 3),
            bench_ret_pct=None if bench is None else round(bench, 3),
            alpha_pct=None if bench is None else round(act - bench, 3),
            error_pp=round(act - exp, 3), abs_error_pp=round(abs(act - exp), 3),
            dir_hit=int((act > 0) == (exp > 0)),
            target_hit=int(h >= row["target_price"] if row["target_price"] > ref else l <= row["target_price"]),
            stop_hit=int(l <= row["stop_price"] if row["stop_price"] < ref else h >= row["stop_price"]),
            evaluated_at=now.isoformat())
        done += 1
    return done


def scorecard(df: pd.DataFrame) -> dict:
    """Plain-python version of the Excel Scorecard, used by the CLI and tests."""
    out = {}
    ev = df[df["status"] == "evaluated"]
    for label, part in (("pick", ev[ev["rank"] == 1]), ("shadow", ev[ev["rank"] > 1])):
        if part.empty:
            out[label] = None
            continue
        out[label] = {
            "n": len(part),
            "direction_hit_rate": part["dir_hit"].mean(),
            "avg_p_up_prior": part["p_up"].mean(),
            "avg_expected_pct": part["exp_ret_pct"].mean(),
            "avg_actual_pct": part["act_ret_pct"].mean(),
            "mean_abs_error_pp": part["abs_error_pp"].mean(),
            "avg_alpha_pct": part["alpha_pct"].mean(),
            "target_hit_rate": part["target_hit"].mean(),
            "stop_hit_rate": part["stop_hit"].mean(),
        }
    return out
