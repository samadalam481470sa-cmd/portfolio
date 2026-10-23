"""Finviz quote-page news table, scraped with BeautifulSoup.

Rows look like:  <td>Oct-12-26 06:02PM</td> ... <a class="tab-link-news" href=...>Headline</a> <span>(Publisher)</span>
Later rows on the same day show only the time ("04:57PM"), so the date carries forward. Times are US/Eastern.
Check Finviz's terms of use before relying on this source.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..fetch.http import FetchError
from ..models import RawArticle
from ..parse.normalize import EASTERN
from .base import Source, register

log = logging.getLogger(__name__)

DATE_RE = re.compile(r"(?P<date>[A-Z][a-z]{2}-\d{2}-\d{2}|Today|Yesterday)?\s*(?P<time>\d{1,2}:\d{2}[AP]M)")


def parse_news_table(html: str, ticker: str, now: datetime | None = None) -> list[RawArticle]:
    now = (now or datetime.now(EASTERN)).astimezone(EASTERN)
    soup = BeautifulSoup(html, "lxml")
    table = soup.find(id="news-table")
    if table is None:
        raise FetchError("finviz: news-table not found (layout changed or blocked)")
    out: list[RawArticle] = []
    current_day: datetime | None = None
    for tr in table.find_all("tr"):
        link = tr.find("a", class_="tab-link-news")
        cell = tr.find("td")
        if not link or not cell:
            continue
        m = DATE_RE.search(cell.get_text(" ", strip=True))
        if not m:
            continue
        day = m.group("date")
        if day == "Today":
            current_day = now
        elif day == "Yesterday":
            current_day = now - timedelta(days=1)
        elif day:
            current_day = datetime.strptime(day, "%b-%d-%y").replace(tzinfo=EASTERN)
        if current_day is None:
            continue
        t = datetime.strptime(m.group("time"), "%I:%M%p")
        published = current_day.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        publisher_span = tr.find("div", class_="news-link-right")
        publisher = publisher_span.get_text(strip=True).strip("()") if publisher_span else ""
        out.append(RawArticle(source="finviz", url=urljoin("https://finviz.com/", link["href"]),
                              title=link.get_text(" ", strip=True), published_at=published,
                              publisher=publisher, ticker_hints=[ticker]))
    return out


@register
class Finviz(Source):
    name = "finviz"

    def fetch(self, tickers: list[str]) -> list[RawArticle]:
        out, errors = [], []
        for t in tickers:
            try:
                resp = self.http.get(f"https://finviz.com/quote.ashx?t={t}", conditional=False)
                out.extend(parse_news_table(resp.text or "", t))
            except FetchError as e:
                errors.append(f"{t}: {e}")
        if errors:
            log.warning("finviz: %d/%d tickers failed, e.g. %s", len(errors), len(tickers), errors[0])
            if len(errors) == len(tickers):
                raise FetchError(errors[0])
        return out
