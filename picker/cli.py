"""python -m picker pick | evaluate | report | export | show"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from functools import partial

from . import config as C
from .data import fetch_history, fetch_ohlc
from .evaluate import evaluate, scorecard
from .export import write_latest
from .llm import NewsScorer
from .news import fetch_headlines
from .pipeline import format_pick, run_pick
from .report import build_report
from .store import Store


def load_universe(path=None, only=None):
    with open(path or C.UNIVERSE_CSV, newline="") as f:
        rows = [(r["symbol"].strip(), r["name"].strip()) for r in csv.DictReader(f)]
    if only:
        wanted = {s.upper() for s in only}
        rows = [r for r in rows if r[0].upper() in wanted]
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="picker", description=__doc__)
    ap.add_argument("command", choices=["pick", "evaluate", "report", "export", "show"])
    ap.add_argument("--exchange", choices=["NSE", "BSE"], default="NSE")
    ap.add_argument("--no-llm", action="store_true", help="use the keyword fallback instead of Llama")
    ap.add_argument("--model", help="Hugging Face model id (default from config / PICKER_LLM)")
    ap.add_argument("--universe", help="CSV with symbol,name columns")
    ap.add_argument("--only", nargs="*", help="limit to these symbols (quick tests)")
    ap.add_argument("--db", help="SQLite path")
    ap.add_argument("--out", default=str(C.REPORT_DIR / "tracker.xlsx"))
    a = ap.parse_args(argv)

    store = Store(a.db)
    now = datetime.now(C.IST)

    if a.command == "pick":
        universe = load_universe(a.universe, a.only)
        rows = run_pick(
            universe, now=now, store=store, exchange=a.exchange,
            history_fn=partial(fetch_history, exchange=a.exchange),
            news_fn=fetch_headlines,
            scorer=NewsScorer(a.model, use_llm=not a.no_llm))
        text = format_pick(rows)
        print(text)
        C.REPORT_DIR.mkdir(exist_ok=True)
        (C.REPORT_DIR / f"pick_{rows[0]['target_date']}.md").write_text(text + "\n")
    elif a.command == "evaluate":
        n = evaluate(store, now=now, ohlc_fn=fetch_ohlc)
        print(f"Evaluated {n} prediction(s).")
        print(_fmt_score(scorecard(store.frame())))
    elif a.command == "report":
        print("Wrote", build_report(store, a.out))
    elif a.command == "export":
        print("Wrote", write_latest(store))
    elif a.command == "show":
        print(_fmt_score(scorecard(store.frame())))


def _fmt_score(sc: dict) -> str:
    lines = []
    for label, s in sc.items():
        if not s:
            lines.append(f"{label}: no evaluated sessions yet")
            continue
        lines.append(
            f"{label}: n={s['n']}  hit {s['direction_hit_rate']:.0%} (prior {s['avg_p_up_prior']:.0%})  "
            f"expected {s['avg_expected_pct']:+.2f}%  actual {s['avg_actual_pct']:+.2f}%  "
            f"MAE {s['mean_abs_error_pp']:.2f}pp  alpha {s['avg_alpha_pct']:+.2f}%")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
