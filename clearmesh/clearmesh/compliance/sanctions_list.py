"""Synthetic sanctions list: normalization, merkle root, content hash."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from unidecode import unidecode

from clearmesh.crypto.merkle import merkle_root


def normalize_name(name: str) -> str:
    s = unidecode(name)
    s = s.casefold()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    tokens = sorted(s.split())
    return " ".join(tokens)


@dataclass(frozen=True, slots=True)
class SanctionsEntry:
    name: str
    aliases: tuple[str, ...]
    entry_id: str


def entry_leaf(entry: SanctionsEntry) -> bytes:
    payload = json.dumps(
        {"id": entry.entry_id, "name": entry.name, "aliases": list(entry.aliases)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload


def list_merkle_root(entries: list[SanctionsEntry]) -> bytes:
    leaves = [entry_leaf(e) for e in sorted(entries, key=lambda x: x.entry_id)]
    return merkle_root(leaves)


def content_hash(entries: list[SanctionsEntry]) -> bytes:
    blob = b"".join(entry_leaf(e) for e in sorted(entries, key=lambda x: x.entry_id))
    return hashlib.sha256(blob).digest()


def default_synthetic_list() -> list[SanctionsEntry]:
    return [
        SanctionsEntry(
            name="Ivan Sanctionov",
            aliases=("Iwan Sanctionov", "Ivan Sanctionoff"),
            entry_id="SYN-001",
        ),
        SanctionsEntry(
            name="Maria Blockova",
            aliases=("Mariya Blockova",),
            entry_id="SYN-002",
        ),
    ]
