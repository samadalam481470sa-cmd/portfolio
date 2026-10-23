"""Near-duplicate detection. Exact duplicates are caught at insert time (URL / normalized title hash);
this catches rewrites of the same story ("Apple shares jump after earnings" vs "Apple stock jumps on earnings")."""
from __future__ import annotations

from rapidfuzz import fuzz

from .normalize import normalize_title


def is_rehash(title: str, earlier_titles: list[str], threshold: int) -> bool:
    t = normalize_title(title)
    return any(fuzz.token_set_ratio(t, normalize_title(e)) >= threshold for e in earlier_titles)
