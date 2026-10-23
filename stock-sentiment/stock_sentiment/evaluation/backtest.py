"""Backtest: does the signal at a day's close predict the following days' returns?

Timing (avoids look-ahead bias):
  * The signal for trading day D uses only articles published at or before 16:00 ET on D.
  * It is compared with the return from D's close to the close h trading days later.
  * News released after the close therefore counts toward the next session, which is when it can be traded.
Returns are reported raw and abnormal (minus the benchmark, SPY by default).
Baselines: random scores (should give IC ~ 0) and 5-day momentum (a cheap signal sentiment should beat).
"""
from __future__ import annotations

from datetime import date, datetime, time

import numpy as np
import pandas as pd

from ..config import Settings
from ..parse.normalize import EASTERN
from ..signals.aggregate import compute_signal, prepare_items
from . import metrics

MARKET_CLOSE = time(16, 0)


def build_panel(items: pd.DataFrame, prices: pd.DataFrame, tickers: list[str], settings: Settings,
                start: date | None = None, end: date | None = None, horizons: tuple[int, ...] = (1, 5)) -> pd.DataFrame:
    px = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    bench = settings.benchmark
    rows = []
    prepared = prepare_items(items, settings) if not items.empty else items
    dates = px.index
    if start:
        dates = dates[dates >= pd.Timestamp(start)]
    if end:
        dates = dates[dates <= pd.Timestamp(end)]
    for t in tickers:
        if t not in px.columns:
            continue
        sub = prepared[prepared["ticker"] == t] if not prepared.empty else prepared
        if sub.empty:
            continue
        first_news = sub["published_at"].min()
        for d in dates:
            as_of = datetime.combine(d.date(), MARKET_CLOSE, tzinfo=EASTERN)
            if pd.Timestamp(as_of) < first_news:
                continue
            sig = compute_signal(sub, as_of, settings.signal)
            row = {"date": d, "ticker": t, **{k: v for k, v in sig.items() if k != "top_headlines"}}
            i = px.index.get_loc(d)
            for h in horizons:
                if i + h < len(px):
                    r = px[t].iloc[i + h] / px[t].iloc[i] - 1
                    row[f"ret_{h}d"] = r
                    if bench in px.columns:
                        row[f"abn_{h}d"] = r - (px[bench].iloc[i + h] / px[bench].iloc[i] - 1)
                else:
                    row[f"ret_{h}d"] = row[f"abn_{h}d"] = np.nan
            if i >= 5:
                row["momentum_5d"] = px[t].iloc[i] / px[t].iloc[i - 5] - 1
            rows.append(row)
    panel = pd.DataFrame(rows)
    if not panel.empty:
        rng = np.random.default_rng(0)
        panel["random"] = rng.standard_normal(len(panel))
    return panel


def evaluate(panel: pd.DataFrame, horizons: tuple[int, ...] = (1, 5)) -> pd.DataFrame:
    """One row per (signal, target) with IC, hit rate and long-short spread."""
    results = []
    with_news = panel[panel["n_articles"] > 0]
    for target in [f"{k}_{h}d" for h in horizons for k in ("ret", "abn")]:
        if target not in panel:
            continue
        for sig in ("composite", "score", "delta", "volume_z", "momentum_5d", "random"):
            if sig not in panel:
                continue
            data = with_news if sig in ("composite", "score", "delta") else panel
            ic = metrics.summarize_ic(metrics.daily_ic(data, sig, target))
            results.append({"signal": sig, "target": target, **ic,
                            **metrics.hit_rate(data, sig, target), **metrics.quantile_spread(data, sig, target)})
    return pd.DataFrame(results)
