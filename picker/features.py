"""Pattern features from ~1 year of daily bars, and the quantitative score."""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

MIN_ROWS = 210  # need a 200-day average plus a little


def _rsi(close: pd.Series, n: int = 14) -> float:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    v = rsi.iloc[-1]
    return 100.0 if math.isnan(v) else float(v)


def compute_features(df: pd.DataFrame, target: date) -> dict | None:
    df = df.dropna(subset=["Close"])
    if len(df) < MIN_ROWS:
        return None
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    pct = c.pct_change() * 100
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    last = float(c.iloc[-1])

    year = df.iloc[-252:]
    hi, lo = float(year["High"].max()), float(year["Low"].min())
    v60 = float(v.iloc[-60:].mean())

    # Same window last year: average daily move over the 3 sessions starting
    # on the date one year before the target session.
    try:
        ly = target.replace(year=target.year - 1)
    except ValueError:
        ly = target - timedelta(days=365)
    i = int(df.index.searchsorted(pd.Timestamp(ly)))
    seg = pct.iloc[i:i + 3]
    seasonal = float(seg.mean()) if i > 0 and len(seg) == 3 else 0.0

    # Weekday behaviour over the last year, for the weekday of the target session.
    recent = pct.iloc[-252:]
    same_dow = recent[recent.index.weekday == target.weekday()].dropna()

    return {
        "asof": df.index[-1].date().isoformat(),
        "close": last,
        "ret_1d": float(pct.iloc[-1]),
        "ret_5d": float((c.iloc[-1] / c.iloc[-6] - 1) * 100),
        "ret_20d": float((c.iloc[-1] / c.iloc[-21] - 1) * 100),
        "ret_60d": float((c.iloc[-1] / c.iloc[-61] - 1) * 100),
        "rsi14": _rsi(c),
        "sma50": float(c.rolling(50).mean().iloc[-1]),
        "sma200": float(c.rolling(200).mean().iloc[-1]),
        "pos52w": (last - lo) / (hi - lo) if hi > lo else 0.5,
        "vol_ratio": float(v.iloc[-5:].mean() / v60) if v60 > 0 else 1.0,
        "atr_pct": float(tr.rolling(14).mean().iloc[-1] / last * 100),
        "seasonal_ret": seasonal,
        "dow_ret": float(same_dow.mean()) if len(same_dow) else 0.0,
        "dow_up_rate": float((same_dow > 0).mean()) if len(same_dow) else 0.5,
    }


def quant_score(f: dict) -> tuple[float, dict]:
    """Blend of trend, momentum, RSI extremes, volume and last-year seasonality.

    Returns a score in [-1, 1] and the parts, so each pick can be explained.
    These weights are a starting hypothesis, not a proven edge; the tracker
    exists to find out whether they work.
    """
    t = math.tanh
    parts = {
        "momentum": 0.25 * t(f["ret_20d"] / 10) + 0.10 * t(f["ret_5d"] / 4),
        "trend": 0.20 * (1 if f["close"] > f["sma50"] else -1)
                 + 0.10 * (1 if f["sma50"] > f["sma200"] else -1),
        "rsi": -0.15 if f["rsi14"] > 75 else (0.10 if f["rsi14"] < 30 else 0.0),
        "volume": 0.10 * t((f["vol_ratio"] - 1) * 1.5) * (1 if f["ret_5d"] >= 0 else -1),
        "seasonal": 0.10 * t(f["seasonal_ret"] / 1.0) + 0.05 * t(f["dow_ret"] / 0.3),
    }
    return max(-1.0, min(1.0, sum(parts.values()))), parts
