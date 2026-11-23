"""Pick for the next session: pattern score -> LLM news read -> one logged pick."""
from __future__ import annotations

import json
from datetime import datetime

from . import config as C
from .tradingdays import next_trading_day
from .data import drop_unfinished_bar
from .features import compute_features, quant_score


def run_pick(universe, *, now: datetime, history_fn, news_fn, scorer, store,
             exchange: str = "NSE", top: int = C.TOP_LOGGED,
             shortlist: int = C.SHORTLIST) -> list[dict]:
    """universe: list of (symbol, name). Returns logged predictions, rank 1 first."""
    hist = history_fn([s for s, _ in universe])
    names = dict(universe)

    bars = {}
    for sym, df in hist.items():
        df = drop_unfinished_bar(df, now)
        if not df.empty:
            bars[sym] = df
    if not bars:
        raise RuntimeError("No market data returned. Check your internet connection.")
    asof = max(df.index[-1] for df in bars.values()).date()
    bars = {s: d for s, d in bars.items() if d.index[-1].date() == asof}  # drop stale/suspended
    target = next_trading_day(asof)

    session_open = datetime.combine(target, C.MARKET_OPEN, tzinfo=C.IST)
    if now >= session_open:
        raise RuntimeError(
            f"The {target} session has already opened; a prediction made now would not be "
            "a fair expectation. Run this after the close of the previous session.")

    # 1) pattern score for everyone
    scored = []
    for sym, df in bars.items():
        f = compute_features(df, target)
        if f is None:
            continue
        q, parts = quant_score(f)
        scored.append({"symbol": sym, "f": f, "quant": q, "parts": parts})
    if not scored:
        raise RuntimeError("Not enough history for any symbol (need ~210 sessions).")
    scored.sort(key=lambda x: x["quant"], reverse=True)

    # 2) news read only for the shortlist (keeps LLM cost low)
    for item in scored[:shortlist]:
        try:
            heads = news_fn(names[item["symbol"]])
        except Exception as e:
            print(f"[news] {item['symbol']}: {e}")
            heads = []
        item["heads"] = heads
        item["news"] = scorer.score(item["symbol"], names[item["symbol"]], heads)
        item["combined"] = C.W_QUANT * item["quant"] + C.W_NEWS * item["news"]["sentiment"]

    ranked = sorted((i for i in scored if "combined" in i), key=lambda x: x["combined"], reverse=True)

    # 3) turn the best into logged expectations
    rows = []
    for rank, it in enumerate(ranked[:top], start=1):
        f, n, comb = it["f"], it["news"], it["combined"]
        ref, atr = f["close"], f["atr_pct"]
        exp_ret = comb * atr * C.EXPECTED_MOVE_ATR_FRACTION
        dist = atr * C.TARGET_ATR_FRACTION
        sign = 1 if comb >= 0 else -1  # a negative score is a DOWN expectation: flip target and stop
        rows.append({
            "created_at": now.isoformat(), "asof_date": asof.isoformat(),
            "target_date": target.isoformat(), "exchange": exchange,
            "symbol": it["symbol"], "name": names[it["symbol"]], "rank": rank,
            "ref_close": round(ref, 2), "atr_pct": round(atr, 3),
            "quant_score": round(it["quant"], 4), "news_score": round(n["sentiment"], 4),
            "combined": round(comb, 4),
            "p_up": round(min(0.95, max(0.05, 0.5 + C.P_UP_SENSITIVITY * comb)), 3),
            "exp_ret_pct": round(exp_ret, 3), "exp_close": round(ref * (1 + exp_ret / 100), 2),
            "target_price": round(ref * (1 + sign * dist / 100), 2),
            "stop_price": round(ref * (1 - sign * dist / 100), 2),
            "news_engine": n["engine"], "catalyst": n["catalyst"], "news_summary": n["summary"],
            "headlines": json.dumps(it["heads"], ensure_ascii=False),
            "features": json.dumps({**{k: round(v, 3) if isinstance(v, float) else v
                                       for k, v in f.items()}, "parts": {k: round(v, 3) for k, v in it["parts"].items()}}),
        })
    store.insert_predictions(rows)
    return rows


def format_pick(rows: list[dict]) -> str:
    p = rows[0]
    feats = json.loads(p["features"])
    weak = "  ** LOW CONVICTION: score below threshold **\n" if p["combined"] < C.LOW_CONVICTION else ""
    lines = [
        f"PICK for session {p['target_date']} ({p['exchange']})  [data as of {p['asof_date']} close]",
        f"  {p['symbol']}  {p['name']}",
        weak.strip() if weak else None,
        f"  Reference close : {p['ref_close']}",
        f"  Expectation     : {'UP' if p['exp_ret_pct'] > 0 else 'DOWN'}  ~{p['exp_ret_pct']:+.2f}% (close ~{p['exp_close']}), "
        f"P(up) prior {p['p_up']:.0%}",
        f"  Target / Stop   : {p['target_price']} / {p['stop_price']}   (ATR {p['atr_pct']:.2f}%)",
        f"  Scores          : pattern {p['quant_score']:+.2f}  news {p['news_score']:+.2f}  "
        f"combined {p['combined']:+.2f}",
        f"  News read       : {p['catalyst']} - {p['news_summary']}  [{p['news_engine']}]",
        f"  Pattern parts   : {feats['parts']}",
        f"  RSI {feats['rsi14']:.0f} | 20d {feats['ret_20d']:+.1f}% | 52w position {feats['pos52w']:.0%} | "
        f"same window last year {feats['seasonal_ret']:+.2f}%/day",
        "",
        "Shadow picks (also tracked, for fairer statistics):",
    ]
    for r in rows[1:]:
        lines.append(f"  #{r['rank']} {r['symbol']:<11} combined {r['combined']:+.2f}  exp {r['exp_ret_pct']:+.2f}%")
    lines += ["", "Experiment, not advice. Past patterns and headlines do not guarantee a next-day move."]
    return "\n".join(l for l in lines if l is not None)
