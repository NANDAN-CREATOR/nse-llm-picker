"""SQLite prediction log. One row per (target session, symbol, exchange)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import DB_PATH

COLUMNS = [
    # identity
    ("created_at", "TEXT"), ("asof_date", "TEXT"), ("target_date", "TEXT"),
    ("exchange", "TEXT"), ("symbol", "TEXT"), ("name", "TEXT"), ("rank", "INTEGER"),
    # expectation (written before the session, never edited)
    ("ref_close", "REAL"), ("atr_pct", "REAL"), ("quant_score", "REAL"),
    ("news_score", "REAL"), ("combined", "REAL"), ("p_up", "REAL"),
    ("exp_ret_pct", "REAL"), ("exp_close", "REAL"), ("target_price", "REAL"),
    ("stop_price", "REAL"), ("news_engine", "TEXT"), ("catalyst", "TEXT"),
    ("news_summary", "TEXT"), ("headlines", "TEXT"), ("features", "TEXT"),
    # reality (filled after the close)
    ("status", "TEXT"), ("act_open", "REAL"), ("act_high", "REAL"), ("act_low", "REAL"),
    ("act_close", "REAL"), ("act_ret_pct", "REAL"), ("gap_pct", "REAL"),
    ("bench_ret_pct", "REAL"), ("alpha_pct", "REAL"), ("error_pp", "REAL"),
    ("abs_error_pp", "REAL"), ("dir_hit", "INTEGER"), ("target_hit", "INTEGER"),
    ("stop_hit", "INTEGER"), ("evaluated_at", "TEXT"),
]
NAMES = [c for c, _ in COLUMNS]
EXPECTATION_COLS = NAMES[:NAMES.index("status")]


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        cols = ", ".join(f"{n} {t}" for n, t in COLUMNS)
        self.con.execute(
            f"CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            f"{cols}, UNIQUE(target_date, symbol, exchange))")
        self.con.commit()

    def insert_predictions(self, rows: list[dict]) -> None:
        """Re-running before the session replaces pending rows; evaluated rows are never touched."""
        for r in rows:
            self.con.execute(
                "DELETE FROM predictions WHERE target_date=? AND exchange=? AND status='pending'",
                (r["target_date"], r["exchange"]))
        for r in rows:
            vals = {n: r.get(n) for n in EXPECTATION_COLS}
            vals["status"] = "pending"
            names = list(vals)
            self.con.execute(
                f"INSERT OR IGNORE INTO predictions ({','.join(names)}) "
                f"VALUES ({','.join('?' * len(names))})", [vals[n] for n in names])
        self.con.commit()

    def pending(self) -> list[sqlite3.Row]:
        return self.con.execute(
            "SELECT * FROM predictions WHERE status='pending' ORDER BY target_date, rank").fetchall()

    def update(self, row_id: int, **fields) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE predictions SET {sets} WHERE id=?", [*fields.values(), row_id])
        self.con.commit()

    def frame(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM predictions ORDER BY target_date, rank", self.con)
