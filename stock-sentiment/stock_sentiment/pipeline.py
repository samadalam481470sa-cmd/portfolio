"""Pipeline stages: fetch -> normalize/dedupe -> link -> score -> signals -> alerts."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .alerts import send_alerts
from .config import Settings
from .db.repo import Repo, utcnow
from .entities.linker import Linker
from .fetch.http import HttpClient
from .parse.dedupe import is_rehash
from .parse.normalize import normalize
from .sentiment.attribution import score_mentions
from .sentiment.models import Scorer, make_scorer
from .signals.aggregate import compute_all
from .sources import REGISTRY

log = logging.getLogger(__name__)
REHASH_WINDOW_HOURS = 48


@dataclass
class Context:
    settings: Settings
    repo: Repo
    http: HttpClient
    linker: Linker
    tickers: list[str]
    _scorers: dict[str, Scorer] | None = None

    @classmethod
    def build(cls, settings: Settings) -> "Context":
        repo = Repo(settings.db_path)
        http = HttpClient(settings.http, repo, settings.raw_cache_dir)
        universe = settings.full_universe()
        return cls(settings, repo, http, Linker(universe, settings.ambiguous_tickers), [e.ticker for e in universe])

    def scorer(self, name: str) -> Scorer:
        if self._scorers is None:
            self._scorers = {}
        if name not in self._scorers:
            self._scorers[name] = make_scorer(name, self.settings.sentiment.batch_size)
        return self._scorers[name]


def run_fetch(ctx: Context, only: list[str] | None = None, tickers: list[str] | None = None) -> dict[str, dict]:
    tickers = tickers or ctx.tickers
    results = {}
    for name, cls in REGISTRY.items():
        cfg = ctx.settings.sources.get(name)
        if (only and name not in only) or (not only and cfg is not None and not cfg.enabled):
            continue
        source = cls(ctx.http, ctx.settings)
        ok, why = source.is_configured()
        if not ok:
            results[name] = {"skipped": why}
            continue
        started = utcnow()
        try:
            raws = source.fetch(tickers)
        except Exception as e:  # one broken source must not stop the others
            log.warning("source %s failed: %s", name, e)
            ctx.repo.record_run(name, started, False, 0, 0, str(e)[:500])
            results[name] = {"error": str(e)}
            continue
        new = 0
        for raw in raws:
            article = normalize(raw)
            if article and ctx.repo.insert_article(article):
                new += 1
        ctx.repo.record_run(name, started, True, len(raws), new)
        results[name] = {"items": len(raws), "new": new}
    return results


def run_link(ctx: Context) -> int:
    threshold = ctx.settings.signal.near_dup_threshold
    n = 0
    for row in ctx.repo.unlinked_articles():
        mentions = ctx.linker.link(row["id"], row["title"], row["summary"] or "", row["body"] or "",
                                   json.loads(row["ticker_hints"] or "[]"))
        for m in mentions:
            earlier = ctx.repo.recent_titles(m.ticker, row["published_at"], REHASH_WINDOW_HOURS)
            if is_rehash(row["title"], earlier, threshold):
                m.novelty = ctx.settings.signal.rehash_novelty
        ctx.repo.save_mentions(row["id"], mentions)
        n += 1
    return n


def run_score(ctx: Context) -> dict[str, int]:
    models = [ctx.settings.sentiment.model]
    if ctx.settings.sentiment.baseline_model and ctx.settings.sentiment.baseline_model not in models:
        models.append(ctx.settings.sentiment.baseline_model)
    out = {}
    for name in models:
        scorer = ctx.scorer(name)
        rows = [dict(r) for r in ctx.repo.unscored_mentions(scorer.name)]
        if rows:
            scores = score_mentions(scorer, ctx.linker, rows)
            ctx.repo.save_sentiment([(r["article_id"], r["ticker"], scorer.name, s) for r, s in zip(rows, scores)])
        out[scorer.name] = len(rows)
    return out


def effective_model(ctx: Context, requested: str | None = None) -> str:
    """The configured model, or VADER if the configured model has never produced scores (e.g. FinBERT failed)."""
    model = requested or ctx.settings.sentiment.model
    has = ctx.repo.conn.execute("SELECT 1 FROM sentiment WHERE model=? LIMIT 1", (model,)).fetchone()
    return model if has else "vader"


def run_signals(ctx: Context, as_of: datetime | None = None, model: str | None = None,
                alert: bool = True) -> list[dict]:
    as_of = as_of or utcnow()
    model = effective_model(ctx, model)
    since_days = ctx.settings.signal.baseline_days + 1
    items = ctx.repo.scored_items(model, ctx.tickers)
    items = items[items["published_at"] > as_of - timedelta(days=since_days)]
    rows = compute_all(items, ctx.tickers, as_of, ctx.settings)
    ctx.repo.save_signals(model, as_of, rows)
    if alert and ctx.settings.alerts.enabled:
        send_alerts(ctx.repo, ctx.settings.alerts, rows, as_of)
    return rows


def run_all(ctx: Context) -> dict:
    fetched = run_fetch(ctx)
    linked = run_link(ctx)
    scored = run_score(ctx)
    signals = run_signals(ctx)
    return {"fetch": fetched, "linked": linked, "scored": scored, "signals": len(signals),
            "as_of": datetime.now(timezone.utc).isoformat()}
