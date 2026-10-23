"""HTML helpers: strip boilerplate and pull readable article text."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

BOILERPLATE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg",
                    "button", "figure"]
BOILERPLATE_HINTS = re.compile(r"(nav|menu|footer|header|sidebar|subscribe|newsletter|promo|advert|ad-|related|"
                               r"share|social|cookie|comment)", re.I)


def html_to_text(fragment: str | None) -> str:
    if not fragment:
        return ""
    if "<" not in fragment:
        return fragment.strip()
    return BeautifulSoup(fragment, "lxml").get_text(" ", strip=True)


def extract_article_text(page_html: str, max_chars: int = 5000) -> str:
    """Best-effort main-text extraction for full article pages (used where pages are accessible)."""
    soup = BeautifulSoup(page_html, "lxml")
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    for tag in soup.find_all(True, attrs={"class": BOILERPLATE_HINTS}):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [p.get_text(" ", strip=True) for p in root.find_all("p")]
    text = " ".join(p for p in paragraphs if len(p.split()) >= 6)
    return text[:max_chars]
