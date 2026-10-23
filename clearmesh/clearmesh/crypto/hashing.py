"""Domain-separated SHA-256."""

from __future__ import annotations

import hashlib

TAGS = (
    "CLEARMESH/TX/v1",
    "CLEARMESH/HDR/v1",
    "CLEARMESH/VOTE/v1",
    "CLEARMESH/PROPOSAL/v1",
    "CLEARMESH/ATTEST/v1",
    "CLEARMESH/ENV/v1",
    "CLEARMESH/RPC/v1",
    "CLEARMESH/HELLO/v1",
    "CLEARMESH/LEAF/v1",
    "CLEARMESH/CYCLE/v1",
    "CLEARMESH/GROUP/v1",
)


def h(tag: str, data: bytes) -> bytes:
    if not isinstance(tag, str) or not tag.startswith("CLEARMESH/"):
        raise ValueError(f"invalid domain tag: {tag!r}")
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    return hashlib.sha256(tag.encode("ascii") + b"\x00" + bytes(data)).digest()
