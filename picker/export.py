"""Writes reports/latest.json: what the Hugging Face Space reads."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config as C
from .evaluate import scorecard
from .store import Store

PICK_FIELDS = ["rank", "symbol", "name", "exchange", "ref_close", "exp_ret_pct", "exp_close",
               "target_price", "stop_price", "p_up", "quant_score", "news_score", "combined",
               "catalyst", "news_summary", "news_engine", "atr_pct"]
HIST_FIELDS = ["target_date", "rank", "symbol", "exp_ret_pct", "act_ret_pct", "error_pp",
               "alpha_pct", "dir_hit", "target_hit", "stop_hit", "p_up"]


def _clean(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in d.items()}


def build_latest(store: Store, now: datetime | None = None) -> dict:
    df = store.frame()
    now = now or datetime.now(C.IST)
    out = {"generated_at": now.isoformat(), "target_date": None, "picks": [],
           "scorecard": {}, "history": []}
    if df.empty:
        return out

    latest = df[df["status"] == "pending"]
    latest = latest if not latest.empty else df[df["target_date"] == df["target_date"].max()]
    target = latest["target_date"].max()
    cur = latest[latest["target_date"] == target].sort_values("rank")
    out["target_date"] = target
    out["asof_date"] = cur["asof_date"].iloc[0]
    for _, r in cur.iterrows():
        d = _clean({k: r[k] for k in PICK_FIELDS})
        d["headlines"] = json.loads(r["headlines"] or "[]")[:5]
        d["low_conviction"] = bool(r["combined"] < C.LOW_CONVICTION)
        out["picks"].append(d)

    out["scorecard"] = {k: (None if v is None else {a: float(b) for a, b in v.items()})
                        for k, v in scorecard(df).items()}
    ev = df[df["status"] == "evaluated"].sort_values(["target_date", "rank"], ascending=[False, True])
    out["history"] = [_clean({k: r[k] for k in HIST_FIELDS}) for _, r in ev.head(300).iterrows()]
    return out


def write_latest(store: Store, path: Path | None = None) -> Path:
    path = Path(path or C.REPORT_DIR / "latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_latest(store), indent=2, default=str))
    return path
