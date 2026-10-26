"""Receipts and double-entry postings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Posting:
    account: str
    asset: str
    delta: int


@dataclass(frozen=True, slots=True)
class Receipt:
    subject: str
    from_status: str | None
    to_status: str
    height: int
    cause: str  # TX | CYCLE | ENGINE
    cause_ref: bytes
    method: str  # GROSS | NETTED | NONE
    reason_code: str
    postings: tuple[Posting, ...]
