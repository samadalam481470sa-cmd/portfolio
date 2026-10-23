"""RSS/Atom based sources."""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from ..fetch.http import FetchError
from ..models import RawArticle
from ..parse.rss import FeedItem, parse_feed
from .base import Source, register

log = logging.getLogger(__name__)


class PerTickerFeed(Source):
    """A feed fetched once per ticker. Collects per-ticker errors and raises only if every ticker failed."""

    def feed_url(self, ticker: str) -> str:
        raise NotImplementedError

    def to_raw(self, item: FeedItem, ticker: str) -> RawArticle:
        return RawArticle(source=self.name, url=item.link, title=item.title, summary=item.summary,
                          published_at=item.published, publisher=item.publisher, ticker_hints=[ticker])

    def fetch(self, tickers: list[str]) -> list[RawArticle]:
        out: list[RawArticle] = []
        errors: list[str] = []
        for t in tickers:
            try:
                resp = self.http.get(self.feed_url(t))
            except FetchError as e:
                errors.append(f"{t}: {e}")
                continue
            if resp.not_modified:
                continue
            out.extend(self.to_raw(item, t) for item in parse_feed(resp.text or ""))
        if errors:
            log.warning("%s: %d/%d tickers failed, e.g. %s", self.name, len(errors), len(tickers), errors[0])
            if len(errors) == len(tickers):
                raise FetchError(errors[0])
        return out


@register
class GoogleNews(PerTickerFeed):
    name = "google_news"

    def feed_url(self, ticker: str) -> str:
        entry = next((u for u in self.settings.universe if u.ticker == ticker), None)
        query = f'"{ticker}" stock' if entry is None else f'"{ticker}" OR "{entry.aliases[0] if entry.aliases else entry.name}" stock'
        return f"https://news.google.com/rss/search?q={quote_plus(query + ' when:7d')}&hl=en-US&gl=US&ceid=US:en"

    def to_raw(self, item: FeedItem, ticker: str) -> RawArticle:
        raw = super().to_raw(item, ticker)
        raw.summary = ""  # Google's description is just the headline again plus the publisher
        return raw


@register
class Nasdaq(PerTickerFeed):
    name = "nasdaq"

    def feed_url(self, ticker: str) -> str:
        return f"https://www.nasdaq.com/feed/rssoutbound?symbol={ticker}"

    def to_raw(self, item: FeedItem, ticker: str) -> RawArticle:
        raw = super().to_raw(item, ticker)
        tagged = [t.strip().upper() for t in item.extra.get("nasdaq:tickers", "").split(",") if t.strip()]
        # Nasdaq tags each item with the tickers it covers; trust that over the query ticker.
        raw.ticker_hints = tagged or [ticker]
        return raw


@register
class Yahoo(PerTickerFeed):
    name = "yahoo"

    def feed_url(self, ticker: str) -> str:
        return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"


@register
class MarketWatch(Source):
    """Market-wide feeds, not per ticker; the linker finds the tickers."""

    name = "marketwatch"
    FEEDS = [
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
        "https://feeds.content.dowjones.io/public/rss/mw_bulletins",
    ]

    def fetch(self, tickers: list[str]) -> list[RawArticle]:
        out, errors = [], []
        for url in self.FEEDS:
            try:
                resp = self.http.get(url)
            except FetchError as e:
                errors.append(str(e))
                continue
            if not resp.not_modified:
                out.extend(RawArticle(source=self.name, url=i.link, title=i.title, summary=i.summary,
                                      published_at=i.published, publisher="MarketWatch")
                           for i in parse_feed(resp.text or ""))
        if errors and len(errors) == len(self.FEEDS):
            raise FetchError(errors[0])
        return out


@register
class Edgar(PerTickerFeed):
    """SEC 8-K filings (material events). The item descriptions are mapped to plain-English text so
    the sentiment model has something to score (e.g. Item 2.02 = earnings release)."""

    name = "edgar"
    ITEM_TEXT = {
        "1.01": "entered into a material definitive agreement",
        "1.02": "terminated a material definitive agreement",
        "1.03": "bankruptcy or receivership",
        "1.05": "material cybersecurity incident",
        "2.01": "completed an acquisition or disposition of assets",
        "2.02": "reported results of operations and financial condition",
        "2.03": "created a direct financial obligation",
        "2.04": "triggering events that accelerate a financial obligation",
        "2.05": "costs associated with exit or disposal activities",
        "2.06": "material impairments",
        "3.01": "notice of delisting or failure to satisfy a listing rule",
        "4.01": "changes in the registrant's certifying accountant",
        "4.02": "non-reliance on previously issued financial statements",
        "5.02": "departure or appointment of directors or officers",
        "7.01": "Regulation FD disclosure",
        "8.01": "other events",
    }
    ITEM_RE = re.compile(r"\d\.\d\d")

    def is_configured(self) -> tuple[bool, str]:
        if not self.settings.http.sec_user_agent:
            return False, "set http.sec_user_agent in config.yaml (SEC requires a contact email)"
        return True, ""

    def feed_url(self, ticker: str) -> str:
        return (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}"
                f"&type=8-K&dateb=&owner=include&count=10&output=atom")

    def fetch(self, tickers: list[str]) -> list[RawArticle]:
        out, errors = [], []
        for t in tickers:
            try:
                resp = self.http.get(self.feed_url(t), user_agent=self.settings.http.sec_user_agent)
            except FetchError as e:
                errors.append(f"{t}: {e}")
                continue
            if resp.not_modified:
                continue
            for item in parse_feed(resp.text or ""):
                items = self.ITEM_RE.findall(item.extra.get("items-desc", ""))
                described = [self.ITEM_TEXT[i] for i in items if i in self.ITEM_TEXT]
                title = f"{t} 8-K filing: " + ("; ".join(described) if described else item.title)
                out.append(RawArticle(source=self.name, url=item.link, title=title, summary="",
                                      published_at=item.published, publisher="SEC EDGAR", ticker_hints=[t]))
        if errors and len(errors) == len(tickers):
            raise FetchError(errors[0])
        return out
