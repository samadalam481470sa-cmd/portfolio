"""Daily price bars from yfinance, cached in SQLite."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from ..db.repo import Repo

log = logging.getLogger(__name__)


def update_prices(repo: Repo, tickers: list[str], start: date | None = None) -> int:
    import yfinance as yf

    default_start = start or (date.today() - timedelta(days=365))
    starts = {}
    for t in tickers:
        last = repo.last_price_date(t)
        starts[t] = (date.fromisoformat(last) - timedelta(days=5)) if last else default_start
    earliest = min(starts.values())
    data = yf.download(tickers, start=earliest.isoformat(), interval="1d", auto_adjust=True,
                       group_by="ticker", progress=False, threads=True)
    if data is None or data.empty:
        log.warning("yfinance returned no data")
        return 0
    frames = []
    for t in tickers:
        try:
            sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
        except KeyError:
            log.warning("no price data for %s", t)
            continue
        sub = sub.dropna(subset=["Close"]).reset_index()
        if sub.empty:
            continue
        frames.append(pd.DataFrame({
            "ticker": t,
            "date": pd.to_datetime(sub["Date"]).dt.strftime("%Y-%m-%d"),
            "open": sub["Open"], "high": sub["High"], "low": sub["Low"],
            "close": sub["Close"], "volume": sub["Volume"],
        }))
    if not frames:
        return 0
    df = pd.concat(frames)
    repo.save_prices(df)
    return len(df)
