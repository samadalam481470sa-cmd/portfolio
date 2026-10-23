"""Bot access control."""

from __future__ import annotations


def parse_allowed_ids(raw: str) -> set[str]:
    if not raw.strip():
        return set()
    return {uid.strip() for uid in raw.split(",") if uid.strip()}
