"""Excel dashboard: Manual | Scorecard (live formulas) | Predictions."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .store import Store

SHOW = ["target_date", "exchange", "symbol", "name", "rank", "status", "ref_close",
        "quant_score", "news_score", "combined", "p_up", "exp_ret_pct", "exp_close",
        "target_price", "stop_price", "act_open", "act_high", "act_low", "act_close",
        "act_ret_pct", "gap_pct", "bench_ret_pct", "alpha_pct", "error_pp",
        "abs_error_pp", "dir_hit", "target_hit", "stop_hit", "catalyst", "news_summary",
        "news_engine", "asof_date", "created_at"]

HEAD = PatternFill("solid", fgColor="1F3A5F")
LAST_ROW = 5000

MANUAL = [
    ("NSE/BSE next-session pick tracker", True),
    ("Experiment, not investment advice. Nothing here is a recommendation to buy or sell.", False),
    ("", False),
    ("How it works", True),
    ("1. Every evening after the close, `python -m picker pick` logs ONE pick (rank 1) plus shadow picks (ranks 2-5) for the next trading session.", False),
    ("2. The expectation (expected %, target, stop, P(up) prior) is written before the session and never edited.", False),
    ("3. After the next close, `python -m picker evaluate` fills in the real open/high/low/close and the gap between expectation and reality.", False),
    ("4. `python -m picker report` rebuilds this workbook. The Scorecard sheet is live formulas over the Predictions sheet.", False),
    ("", False),
    ("Reading the Scorecard", True),
    ("Direction hit rate: share of picks where the sign of the move matched the expectation (UP).", False),
    ("P(up) prior vs hit rate: if the prior says 60% but the real rate is 48%, the model is over-confident.", False),
    ("Mean abs error (pp): average gap between expected % and actual %, in percentage points. Compare with the stock's ATR%.", False),
    ("Alpha: actual return minus Nifty 50 return over the same window. Positive alpha is what matters, not just up days.", False),
    ("Target / stop hit: whether the day's high reached the target or the low touched the stop. If both are 1, the order is unknown.", False),
    ("Shadow picks: ranks 2-5 are tracked too, so you get ~5x more samples than the single pick. Compare pick vs shadow to see if rank 1 is really better.", False),
    ("", False),
    ("Be careful", True),
    ("A handful of days proves nothing. Expect noise for at least 30-60 sessions before trusting any hit rate.", False),
    ("Returns are measured close-to-close from the reference close, so they include the overnight gap.", False),
    ("The pick is a hypothesis about a single day. Costs, slippage and taxes are not modelled.", False),
]


def _scorecard(ws, cols: dict):
    def rng(name):
        c = get_column_letter(cols[name])
        return f"Predictions!${c}$2:${c}${LAST_ROW}"

    ws.append(["Metric", "Rank-1 pick", "Shadow picks (rank 2+)"])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEAD

    def crit(kind):  # criteria pairs for COUNTIFS/AVERAGEIFS
        rank = '1' if kind == "pick" else '">1"'
        return f'{rng("rank")},{rank},{rng("status")},"evaluated"'

    def avg(col, kind):
        return f'=IFERROR(AVERAGEIFS({rng(col)},{crit(kind)}),"-")'

    def n(kind):
        return f"=COUNTIFS({crit(kind)})"

    def rate(col, kind):
        return f'=IFERROR(COUNTIFS({crit(kind)},{rng(col)},1)/COUNTIFS({crit(kind)}),"-")'

    rows = [
        ("Sessions evaluated", n("pick"), n("shadow"), "0"),
        ("Direction hit rate", rate("dir_hit", "pick"), rate("dir_hit", "shadow"), "0.0%"),
        ("Avg P(up) prior (what we believed)", avg("p_up", "pick"), avg("p_up", "shadow"), "0.0%"),
        ("Avg expected return %", avg("exp_ret_pct", "pick"), avg("exp_ret_pct", "shadow"), "0.00"),
        ("Avg actual return %", avg("act_ret_pct", "pick"), avg("act_ret_pct", "shadow"), "0.00"),
        ("Mean abs error (pp)", avg("abs_error_pp", "pick"), avg("abs_error_pp", "shadow"), "0.00"),
        ("Avg error (actual - expected, pp)", avg("error_pp", "pick"), avg("error_pp", "shadow"), "0.00"),
        ("Avg alpha vs Nifty 50 %", avg("alpha_pct", "pick"), avg("alpha_pct", "shadow"), "0.00"),
        ("Target hit rate", rate("target_hit", "pick"), rate("target_hit", "shadow"), "0.0%"),
        ("Stop hit rate", rate("stop_hit", "pick"), rate("stop_hit", "shadow"), "0.0%"),
    ]
    for label, f1, f2, fmt in rows:
        ws.append([label, f1, f2])
        for col in (2, 3):
            ws.cell(ws.max_row, col).number_format = fmt
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 24


def build_report(store: Store, path: str | Path) -> Path:
    df = store.frame()
    wb = Workbook()

    man = wb.active
    man.title = "Manual"
    for text, bold in MANUAL:
        man.append([text])
        man.cell(man.max_row, 1).font = Font(bold=bold, size=13 if bold else 11)
        man.cell(man.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    man.column_dimensions["A"].width = 130

    pred = wb.create_sheet("Predictions")
    pred.append(SHOW)
    for c in pred[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEAD
    for _, r in df.iterrows():
        pred.append([None if (v != v) else v for v in (r.get(c) for c in SHOW)])
    for i, name in enumerate(SHOW, start=1):
        pred.column_dimensions[get_column_letter(i)].width = max(11, min(40, len(name) + 3))
    pred.freeze_panes = "E2"
    cols = {name: i for i, name in enumerate(SHOW, start=1)}

    sc = wb.create_sheet("Scorecard", 1)
    _scorecard(sc, cols)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
