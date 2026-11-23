"""Market data via yfinance (imported lazily so tests run without it)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from .config import DATA_READY

SUFFIX = {"NSE": ".NS", "BSE": ".BO"}


def yahoo_ticker(symbol: str, exchange: str = "NSE") -> str:
    return symbol if symbol.startswith("^") else symbol + SUFFIX[exchange]


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(how="all").copy()
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


def fetch_history(symbols, exchange: str = "NSE", period: str = "2y") -> dict:
    """Daily OHLCV for many symbols. Symbols that fail are left out."""
    import yfinance as yf

    tickers = [yahoo_ticker(s, exchange) for s in symbols]
    raw = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                      auto_adjust=False, progress=False, threads=True)
    out = {}
    for sym, tkr in zip(symbols, tickers):
        try:
            df = _clean(raw[tkr])
        except KeyError:
            continue
        if not df.empty:
            out[sym] = df
    return out


def fetch_ohlc(symbol: str, exchange: str, start: date, end: date) -> pd.DataFrame:
    """Daily bars between start and end (inclusive) for one symbol or index."""
    import yfinance as yf

    df = yf.download(yahoo_ticker(symbol, exchange), start=start.isoformat(),
                     end=(end + timedelta(days=1)).isoformat(), interval="1d",
                     auto_adjust=False, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return _clean(df)


def drop_unfinished_bar(df: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Remove today's bar if the session is still open (it is partial)."""
    if df.empty:
        return df
    if df.index[-1].date() == now.date() and now.time() < DATA_READY:
        return df.iloc[:-1]
    return df
