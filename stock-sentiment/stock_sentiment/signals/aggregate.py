"""Turn scored mentions into a per-ticker signal as of a point in time.

For a ticker at time T, each article i published in (T - lookback, T] gets weight
    w_i = relevance_i * novelty_i * source_weight_i * 0.5 ** (age_hours_i / half_life)
and
    score      = sum(w_i * compound_i) / sum(w_i)                  tone of recent news, in [-1, 1]
    baseline   = relevance-weighted mean compound over the prior baseline_days (0 if too little data)
    delta      = score - baseline                                  tone vs this stock's normal coverage
    volume_z   = (articles in last 24h - mean daily count) / std   unusual news flow
    confidence = 1 - exp(-sum(w_i) / k)                            how much evidence there is
    composite  = confidence * (score + delta) / 2                  what we rank on

The same function powers live signals and the backtest, and it only looks at articles published at or
before T, so the backtest can't peek at the future.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..config import Settings, SignalConfig

MIN_BASELINE_ITEMS = 5
MIN_VOLUME_STD = 0.5
MIN_VOLUME_HISTORY_DAYS = 7


def prepare_items(items: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    df = items.copy()
    df["source_weight"] = df["source"].map(settings.source_weight).astype(float)
    return df.sort_values("published_at")


def compute_signal(items: pd.DataFrame, as_of: datetime, cfg: SignalConfig) -> dict:
    """items: one ticker's rows from prepare_items (published_at, compound, relevance, novelty, source_weight)."""
    as_of = pd.Timestamp(as_of)
    lookback_start = as_of - timedelta(hours=cfg.lookback_hours)
    baseline_start = as_of - timedelta(days=cfg.baseline_days)
    past = items[items["published_at"] <= as_of]
    recent = past[past["published_at"] > lookback_start]

    if recent.empty:
        score, total_w, top = 0.0, 0.0, []
    else:
        age_h = (as_of - recent["published_at"]).dt.total_seconds() / 3600
        w = recent["relevance"] * recent["novelty"] * recent["source_weight"] * np.power(0.5, age_h / cfg.half_life_hours)
        total_w = float(w.sum())
        score = float((w * recent["compound"]).sum() / total_w) if total_w > 0 else 0.0
        impact = (w * recent["compound"].abs()).sort_values(ascending=False)
        top = [{"title": recent.at[i, "title"], "url": recent.at[i, "url"], "publisher": recent.at[i, "publisher"],
                "compound": round(float(recent.at[i, "compound"]), 3),
                "published_at": recent.at[i, "published_at"].isoformat()}
               for i in impact.index[:3]]

    hist = past[(past["published_at"] > baseline_start) & (past["published_at"] <= lookback_start)]
    if len(hist) >= MIN_BASELINE_ITEMS:
        baseline = float(np.average(hist["compound"], weights=hist["relevance"].clip(lower=1e-6)))
    else:
        baseline = 0.0
    delta = score - baseline if not recent.empty else 0.0

    last24 = int((past["published_at"] > as_of - timedelta(hours=24)).sum())
    window = past[past["published_at"] > baseline_start]
    # Volume spikes are meaningless until there is enough history to know what "normal" is.
    if window.empty or (as_of - window["published_at"].min()) < timedelta(days=MIN_VOLUME_HISTORY_DAYS):
        volume_z = 0.0
    else:
        days_back = ((as_of - window["published_at"]).dt.total_seconds() // 86400).astype(int)
        daily = np.bincount(days_back.clip(upper=cfg.baseline_days - 1), minlength=cfg.baseline_days)[1:]
        volume_z = float((last24 - daily.mean()) / max(daily.std(), MIN_VOLUME_STD))

    confidence = 1 - math.exp(-total_w / cfg.confidence_k)
    return {
        "score": round(score, 4),
        "baseline": round(baseline, 4),
        "delta": round(delta, 4),
        "volume_z": round(volume_z, 3),
        "confidence": round(confidence, 4),
        "composite": round(confidence * (score + delta) / 2, 4),
        "n_articles": int(len(recent)),
        "top_headlines": top,
    }


def compute_all(items: pd.DataFrame, tickers: list[str], as_of: datetime, settings: Settings) -> list[dict]:
    prepared = prepare_items(items, settings) if not items.empty else items
    out = []
    for t in tickers:
        sub = prepared[prepared["ticker"] == t] if not prepared.empty else prepared
        if sub.empty:
            sub = pd.DataFrame(columns=["published_at", "compound", "relevance", "novelty", "source_weight",
                                        "title", "url", "publisher"])
            sub["published_at"] = pd.to_datetime(sub["published_at"], utc=True)
        out.append({"ticker": t, **compute_signal(sub, as_of, settings.signal)})
    return out
