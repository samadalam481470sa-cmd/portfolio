"""Signal-quality metrics."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def daily_ic(panel: pd.DataFrame, signal_col: str, return_col: str, min_names: int = 5) -> pd.Series:
    """Spearman rank correlation between signal and forward return, computed across tickers each day."""
    def one_day(g: pd.DataFrame) -> float:
        g = g[[signal_col, return_col]].dropna()
        if len(g) < min_names or g[signal_col].nunique() < 2:
            return np.nan
        return g[signal_col].rank().corr(g[return_col].rank())

    return panel.groupby("date")[[signal_col, return_col]].apply(one_day).dropna()


def summarize_ic(ic: pd.Series) -> dict:
    n = len(ic)
    if n == 0:
        return {"ic_mean": np.nan, "ic_std": np.nan, "ic_t": np.nan, "days": 0}
    std = ic.std(ddof=1) if n > 1 else np.nan
    t = ic.mean() / (std / math.sqrt(n)) if n > 1 and std > 0 else np.nan
    return {"ic_mean": ic.mean(), "ic_std": std, "ic_t": t, "days": n}


def hit_rate(panel: pd.DataFrame, signal_col: str, return_col: str, min_abs: float = 0.0) -> dict:
    g = panel[[signal_col, return_col]].dropna()
    g = g[(g[signal_col].abs() > min_abs) & (g[return_col] != 0)]
    if g.empty:
        return {"hit_rate": np.nan, "n": 0}
    hits = (np.sign(g[signal_col]) == np.sign(g[return_col])).mean()
    return {"hit_rate": float(hits), "n": int(len(g))}


def quantile_spread(panel: pd.DataFrame, signal_col: str, return_col: str, q: int = 5) -> dict:
    """Average daily return of the top-quantile names minus the bottom-quantile names."""
    spreads = []
    for _, g in panel.groupby("date"):
        g = g[[signal_col, return_col]].dropna()
        if len(g) < q or g[signal_col].nunique() < 2:
            continue
        ranks = g[signal_col].rank(method="first")
        buckets = pd.qcut(ranks, q, labels=False)
        spreads.append(g[return_col][buckets == q - 1].mean() - g[return_col][buckets == 0].mean())
    if not spreads:
        return {"ls_mean": np.nan, "ls_days": 0}
    s = pd.Series(spreads)
    return {"ls_mean": float(s.mean()), "ls_days": len(s),
            "ls_t": float(s.mean() / (s.std(ddof=1) / math.sqrt(len(s)))) if len(s) > 1 and s.std() > 0 else np.nan}
