"""Fetch real-time news from public RSS feeds and optional API sources."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import httpx

from market_agent.ai.models import NewsItem

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
FINNHUB_NEWS = "https://finnhub.io/api/v1/company-news"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketAgent/1.0)"}


class NewsFetcher:
    def __init__(self, finnhub_api_key: str = "") -> None:
        self.finnhub_api_key = finnhub_api_key
        self._client = httpx.AsyncClient(timeout=20.0, headers=HEADERS)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_stock_news(self, symbol: str, limit: int = 10) -> list[NewsItem]:
        """Fetch news from Finnhub (if key set) + Google News RSS."""
        items: list[NewsItem] = []
        seen_titles: set[str] = set()

        if self.finnhub_api_key:
            finnhub_items = await self._fetch_finnhub(symbol, limit)
            for item in finnhub_items:
                key = item.title.lower()[:80]
                if key not in seen_titles:
                    seen_titles.add(key)
                    items.append(item)

        rss_items = await self._fetch_google_rss(f"{symbol} stock", limit)
        for item in rss_items:
            key = item.title.lower()[:80]
            if key not in seen_titles:
                seen_titles.add(key)
                items.append(item)

        return items[:limit]

    async def search_news(self, query: str, limit: int = 10) -> list[NewsItem]:
        return (await self._fetch_google_rss(query, limit))[:limit]

    async def _fetch_finnhub(self, symbol: str, limit: int) -> list[NewsItem]:
        from datetime import date, timedelta

        today = date.today()
        week_ago = today - timedelta(days=7)
        resp = await self._client.get(
            FINNHUB_NEWS,
            params={
                "symbol": symbol.upper(),
                "from": week_ago.isoformat(),
                "to": today.isoformat(),
                "token": self.finnhub_api_key,
            },
        )
        if resp.status_code != 200:
            return []
        return [
            NewsItem(
                title=a.get("headline", ""),
                source=a.get("source", "Finnhub"),
                url=a.get("url", ""),
                published=str(a.get("datetime", "")),
                summary=a.get("summary", "")[:300],
            )
            for a in resp.json()[:limit]
        ]

    async def _fetch_google_rss(self, query: str, limit: int) -> list[NewsItem]:
        url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))
        resp = await self._client.get(url)
        if resp.status_code != 200:
            return []
        return _parse_rss(resp.text, limit)


def _parse_rss(xml_text: str, limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title = _text(item, "title")
            if not title:
                continue
            items.append(
                NewsItem(
                    title=unescape(title),
                    source=_text(item, "source") or "Google News",
                    url=_text(item, "link") or "",
                    published=_text(item, "pubDate") or "",
                )
            )
            if len(items) >= limit:
                break
    except ET.ParseError:
        pass
    return items


def _text(parent: ET.Element, tag: str) -> str:
    el = parent.find(tag)
    return (el.text or "").strip() if el is not None else ""
