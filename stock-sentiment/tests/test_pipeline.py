"""End-to-end run against a fake source and a temporary database (no network)."""
from datetime import datetime, timedelta, timezone

from stock_sentiment import pipeline
from stock_sentiment.config import Settings, SourceConfig, TickerEntry
from stock_sentiment.models import RawArticle
from stock_sentiment.sources.base import REGISTRY, Source

NOW = datetime.now(timezone.utc)


class FakeSource(Source):
    name = "fake"

    def fetch(self, tickers):
        return [
            RawArticle("fake", "https://x.com/1?utm_source=a", "Nvidia shares soar to record on blowout earnings",
                       published_at=NOW - timedelta(hours=2), publisher="Wire"),
            RawArticle("fake", "https://x.com/1", "Nvidia shares soar to record on blowout earnings",
                       published_at=NOW - timedelta(hours=2), publisher="Wire"),  # same URL after canonicalizing
            RawArticle("fake", "https://y.com/2", "Intel stock plunges after disastrous guidance and layoffs",
                       published_at=NOW - timedelta(hours=1), publisher="Wire"),
            RawArticle("fake", "https://z.com/3", "Nvidia shares soar to a record on blowout earnings!",
                       published_at=NOW - timedelta(hours=1), publisher="Other"),  # rehash
        ]


class BrokenSource(Source):
    name = "broken"

    def fetch(self, tickers):
        raise RuntimeError("layout changed")


def test_full_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REGISTRY", {"fake": FakeSource, "broken": BrokenSource})
    settings = Settings(db_path=tmp_path / "t.db", raw_cache_dir=tmp_path / "raw", universe_file=None,
                        sources={"fake": SourceConfig(), "broken": SourceConfig()},
                        universe=[TickerEntry(ticker="NVDA", name="NVIDIA Corporation", aliases=["Nvidia"]),
                                  TickerEntry(ticker="INTC", name="Intel Corporation", aliases=["Intel"])])
    settings.sentiment.model = "vader"
    settings.sentiment.baseline_model = None
    ctx = pipeline.Context.build(settings)

    fetched = pipeline.run_fetch(ctx)
    assert fetched["fake"] == {"items": 4, "new": 3}  # exact URL duplicate dropped
    assert "error" in fetched["broken"]
    assert pipeline.run_link(ctx) == 3
    novelty = dict(ctx.repo.conn.execute(
        "SELECT a.url, m.novelty FROM mentions m JOIN articles a ON a.id = m.article_id").fetchall())
    assert novelty["https://z.com/3"] == settings.signal.rehash_novelty  # reworded copy of an earlier headline
    assert novelty["https://x.com/1"] == 1.0
    assert pipeline.run_score(ctx)["vader"] >= 2

    rows = {r["ticker"]: r for r in pipeline.run_signals(ctx)}
    assert rows["NVDA"]["score"] > 0 > rows["INTC"]["score"]

    health = ctx.repo.source_health().set_index("source")
    assert health.loc["broken", "ok_runs"] == 0 and health.loc["fake", "ok_runs"] == 1

    # A second run finds nothing new.
    assert pipeline.run_fetch(ctx)["fake"]["new"] == 0


def test_registry_has_real_sources():
    assert {"nasdaq", "finviz", "marketwatch", "edgar", "google_news", "yahoo"} <= set(REGISTRY)
