"""Proven statement builder."""

from __future__ import annotations

from clearmesh.iso20022.camt053 import build_statement


def build_proven_statement(
    pid: str,
    receipts: list[dict],
    opening: int,
    closing: int,
    fmt: str = "json",
) -> str | dict:
    entries = []
    for r in receipts:
        for p in r.get("postings", []):
            if p.get("account") != pid:
                continue
            entries.append(
                {
                    "amount": abs(int(p["delta"])),
                    "cdi": "CRDT" if int(p["delta"]) > 0 else "DBIT",
                    "status": r.get("to_status", ""),
                    "ref": r.get("subject", ""),
                }
            )
    if fmt == "camt053":
        return build_statement(pid, entries, opening, closing)
    return {
        "participant": pid,
        "opening": opening,
        "closing": closing,
        "entries": entries,
    }
