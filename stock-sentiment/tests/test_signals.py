from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from stock_sentiment.config import Settings, SignalConfig, SourceConfig
from stock_sentiment.evaluation import metrics
from stock_sentiment.evaluation.backtest import build_panel, evaluate
from stock_sentiment.sentiment.models import VaderScorer
from stock_sentiment.signals.aggregate import compute_signal

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
CFG = SignalConfig()


def items(rows):
    df = pd.DataFrame(rows, columns=["published_at", "compound", "relevance", "novelty", "source_weight"])
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    df["title"], df["url"], df["publisher"] = "t", "u", "p"
    return df


def test_empty_signal_is_neutral():
    s = compute_signal(items([]), NOW, CFG)
    assert s["score"] == 0 and s["confidence"] == 0 and s["n_articles"] == 0 and s["composite"] == 0


def test_recent_news_outweighs_old_news():
    s = compute_signal(items([(NOW - timedelta(hours=1), 0.8, 1, 1, 1),
                              (NOW - timedelta(hours=60), -0.8, 1, 1, 1)]), NOW, CFG)
    assert s["score"] > 0.5


def test_future_articles_are_ignored():
    s = compute_signal(items([(NOW + timedelta(hours=1), 1.0, 1, 1, 1)]), NOW, CFG)
    assert s["n_articles"] == 0 and s["score"] == 0


def test_delta_is_relative_to_baseline():
    old = [(NOW - timedelta(days=d), 0.6, 1, 1, 1) for d in range(5, 15)]
    s = compute_signal(items(old + [(NOW - timedelta(hours=2), 0.6, 1, 1, 1)]), NOW, CFG)
    assert s["baseline"] == pytest.approx(0.6)
    assert s["delta"] == pytest.approx(0.0)


def test_volume_spike_needs_history():
    burst = [(NOW - timedelta(hours=h), 0.1, 1, 1, 1) for h in range(10)]
    assert compute_signal(items(burst), NOW, CFG)["volume_z"] == 0
    history = [(NOW - timedelta(days=d), 0.1, 1, 1, 1) for d in range(2, 20)]
    assert compute_signal(items(history + burst), NOW, CFG)["volume_z"] > 3


def test_more_evidence_more_confidence():
    one = compute_signal(items([(NOW, 0.5, 1, 1, 1)]), NOW, CFG)["confidence"]
    many = compute_signal(items([(NOW, 0.5, 1, 1, 1)] * 6), NOW, CFG)["confidence"]
    assert many > one


def test_vader_scores_direction():
    v = VaderScorer()
    good, bad = v.score_batch(["Profits surge to a record, great quarter", "Terrible losses and a lawsuit"])
    assert good.compound > 0 > bad.compound


def test_ic_detects_a_perfect_signal_and_not_noise():
    rng = np.random.default_rng(1)
    rows = []
    for d in pd.bdate_range("2026-01-01", periods=30):
        r = rng.standard_normal(10)
        rows += [{"date": d, "ticker": i, "sig": r[i], "noise": rng.standard_normal(), "ret": r[i]} for i in range(10)]
    panel = pd.DataFrame(rows)
    assert metrics.summarize_ic(metrics.daily_ic(panel, "sig", "ret"))["ic_mean"] == pytest.approx(1.0)
    assert abs(metrics.summarize_ic(metrics.daily_ic(panel, "noise", "ret"))["ic_mean"]) < 0.2
    assert metrics.hit_rate(panel, "sig", "ret")["hit_rate"] == 1.0
    assert metrics.quantile_spread(panel, "sig", "ret")["ls_mean"] > 0


def test_backtest_uses_only_news_before_the_close():
    """News at 17:00 ET on day D must not affect day D's signal; it shows up on D+1."""
    settings = Settings(sources={"x": SourceConfig()})
    dates = pd.bdate_range("2026-10-05", periods=6)
    prices = pd.DataFrame([{"ticker": t, "date": d, "close": 100 + i} for t in ("AAA", "SPY")
                           for i, d in enumerate(dates)])
    after_close = pd.Timestamp("2026-10-06 17:00", tz="America/New_York").tz_convert("UTC")
    news = pd.DataFrame([{"ticker": "AAA", "published_at": pd.Timestamp("2026-10-05 13:00", tz="UTC"), "compound": 0.0,
                          "relevance": 1.0, "novelty": 1.0, "source": "x", "title": "a", "url": "u", "publisher": "p"},
                         {"ticker": "AAA", "published_at": after_close, "compound": 0.9, "relevance": 1.0,
                          "novelty": 1.0, "source": "x", "title": "b", "url": "u", "publisher": "p"}])
    panel = build_panel(news, prices, ["AAA"], settings).set_index("date")
    assert panel.loc["2026-10-06", "score"] == 0.0
    assert panel.loc["2026-10-07", "score"] > 0.5
    assert panel.loc["2026-10-06", "ret_1d"] == pytest.approx(102 / 101 - 1)
    assert panel.loc["2026-10-06", "abn_1d"] == pytest.approx(0.0)
    assert not evaluate(panel.reset_index()).empty
