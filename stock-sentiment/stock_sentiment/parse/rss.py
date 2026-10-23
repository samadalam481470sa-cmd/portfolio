"""Generic RSS 2.0 / Atom parsing with BeautifulSoup's XML parser."""
from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from .html import html_to_text


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str = ""
    published: str = ""
    publisher: str = ""
    guid: str = ""
    categories: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_feed(xml: str) -> list[FeedItem]:
    soup = BeautifulSoup(xml, "xml")
    items = soup.find_all("item")
    if items:
        return [_parse_rss_item(i) for i in items]
    return [_parse_atom_entry(e) for e in soup.find_all("entry")]


def _parse_rss_item(item) -> FeedItem:
    source = item.find("source")
    creator = item.find("creator")  # dc:creator
    extra = {}
    for child in item.find_all(True, recursive=False):
        if child.prefix and child.prefix not in ("dc", "media", "content"):
            extra[f"{child.prefix}:{child.name}"] = _text(child)
    description = item.find("description")
    return FeedItem(
        title=_text(item.find("title")),
        link=_text(item.find("link")) or _text(item.find("guid")),
        summary=html_to_text(description.string or _text(description)) if description else "",
        published=_text(item.find("pubDate")) or _text(item.find("date")),
        publisher=_text(source) or _text(creator),
        guid=_text(item.find("guid")),
        categories=[_text(c) for c in item.find_all("category")],
        extra=extra,
    )


def _parse_atom_entry(entry) -> FeedItem:
    link = entry.find("link", rel="alternate") or entry.find("link")
    summary = entry.find("summary") or entry.find("content")
    extra = {}
    content = entry.find("content")
    if content:
        for child in content.find_all(True):
            if not child.find(True):
                extra[child.name] = _text(child)
    return FeedItem(
        title=_text(entry.find("title")),
        link=link.get("href", "") if link else "",
        summary=html_to_text(summary.string or _text(summary)) if summary else "",
        published=_text(entry.find("published")) or _text(entry.find("updated")),
        publisher=_text(entry.find("author")),
        guid=_text(entry.find("id")),
        categories=[c.get("term", "") for c in entry.find_all("category")],
        extra=extra,
    )
