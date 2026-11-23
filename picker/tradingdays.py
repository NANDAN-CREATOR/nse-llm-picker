"""Trading-day logic. Holidays come from data/holidays.csv (edit it each year)."""
import csv
from datetime import date, timedelta
from functools import lru_cache

from .config import HOLIDAYS_CSV


@lru_cache(maxsize=1)
def holidays() -> frozenset:
    out = set()
    if HOLIDAYS_CSV.exists():
        with open(HOLIDAYS_CSV, newline="") as f:
            for row in csv.DictReader(f):
                out.add(date.fromisoformat(row["date"]))
    return frozenset(out)


def is_trading_day(d: date, extra_holidays=()) -> bool:
    return d.weekday() < 5 and d not in holidays() and d not in set(extra_holidays)


def next_trading_day(after: date, extra_holidays=()) -> date:
    d = after + timedelta(days=1)
    while not is_trading_day(d, extra_holidays):
        d += timedelta(days=1)
    return d
