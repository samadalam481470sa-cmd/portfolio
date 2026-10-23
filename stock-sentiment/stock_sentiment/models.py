"""Core data shapes passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawArticle:
    """An article as produced by a source, before normalization."""

    source: str
    url: str
    title: str
    summary: str = ""
    body: str = ""
    published_at: datetime | None = None
    publisher: str = ""
    # Tickers the source itself associates with the item (feed metadata or the query that found it).
    ticker_hints: list[str] = field(default_factory=list)


@dataclass
class Article:
    """A normalized, deduplicatable article ready for storage."""

    id: str
    source: str
    url: str
    title: str
    summary: str
    body: str
    published_at: datetime  # timezone-aware UTC
    fetched_at: datetime
    publisher: str
    title_hash: str
    ticker_hints: list[str] = field(default_factory=list)


@dataclass
class Mention:
    article_id: str
    ticker: str
    relevance: float
    location: str  # headline | lead | body | hint
    novelty: float = 1.0


@dataclass
class SentimentScore:
    pos: float
    neg: float
    neu: float
    compound: float  # in [-1, 1]; positive is bullish
