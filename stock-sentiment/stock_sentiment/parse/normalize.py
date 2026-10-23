"""Turn RawArticles into normalized Articles: clean text, UTC dates, canonical URLs, stable ids."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dateutil import parser as dateparser
from dateutil import tz

from ..models import Article, RawArticle

EASTERN = tz.gettz("America/New_York")
TRACKING_PARAMS = re.compile(r"^(utm_|mod$|guccounter|ncid|yptr|cmpid|ref$|src$|.*_source$|siteid$|time$)")
WS = re.compile(r"\s+")


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return WS.sub(" ", text).strip()


def parse_date(value: str | datetime | None, default_tz=timezone.utc) -> datetime | None:
    """Parse any feed date into timezone-aware UTC. Naive values are interpreted in default_tz."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = dateparser.parse(str(value), tzinfos={"ET": EASTERN, "EST": EASTERN, "EDT": EASTERN})
        except (ValueError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt.astimezone(timezone.utc)


def canonical_url(url: str) -> str:
    p = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if not TRACKING_PARAMS.match(k.lower())]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower() or "https", p.netloc.lower().removeprefix("www."), path, "",
                       urlencode(query), ""))


def normalize_title(title: str) -> str:
    t = clean_text(title).lower()
    t = re.sub(r"[^\w\s$]", " ", t)
    return WS.sub(" ", t).strip()


def title_hash(title: str) -> str:
    return hashlib.sha1(normalize_title(title).encode()).hexdigest()


def strip_publisher_suffix(title: str, publisher: str) -> str:
    """Google News appends ' - Publisher' to every headline."""
    if publisher and title.endswith(f" - {publisher}"):
        return title[: -len(publisher) - 3].rstrip()
    return title


def normalize(raw: RawArticle, now: datetime | None = None) -> Article | None:
    now = now or datetime.now(timezone.utc)
    title = clean_text(raw.title)
    if not title or not raw.url:
        return None
    publisher = clean_text(raw.publisher)
    title = strip_publisher_suffix(title, publisher)
    summary = clean_text(raw.summary)
    if normalize_title(summary) == normalize_title(title):
        summary = ""
    published = parse_date(raw.published_at) or now
    if published > now:  # clock skew or bad feed data; never let an article live in the future
        published = now
    url = canonical_url(raw.url)
    return Article(
        id=hashlib.sha1(url.encode()).hexdigest()[:20],
        source=raw.source,
        url=url,
        title=title,
        summary=summary,
        body=clean_text(raw.body),
        published_at=published,
        fetched_at=now,
        publisher=publisher,
        title_hash=title_hash(title),
        ticker_hints=[t.upper() for t in raw.ticker_hints],
    )
