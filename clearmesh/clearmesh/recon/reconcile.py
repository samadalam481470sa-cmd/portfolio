"""Ledger CSV vs proven receipts -> breaks report."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Break:
    kind: str
    uetr: str
    detail: str


def reconcile_csv(
    ledger_path: str | Path,
    chain_rows: list[dict],
) -> list[Break]:
    """
    ledger CSV columns: uetr,amount,status
    chain_rows: same shape from proven receipts
    """
    with open(ledger_path, newline="", encoding="utf-8") as f:
        internal = {r["uetr"]: r for r in csv.DictReader(f)}
    chain = {r["uetr"]: r for r in chain_rows}
    breaks: list[Break] = []
    for uetr, row in chain.items():
        if uetr not in internal:
            breaks.append(Break("MISSING_INTERNALLY", uetr, "on-chain only"))
            continue
        ir = internal[uetr]
        if str(ir.get("amount")) != str(row.get("amount")):
            breaks.append(
                Break(
                    "AMOUNT_MISMATCH",
                    uetr,
                    f"internal={ir.get('amount')} chain={row.get('amount')}",
                )
            )
        if str(ir.get("status")) != str(row.get("status")):
            breaks.append(
                Break(
                    "STATUS_MISMATCH",
                    uetr,
                    f"internal={ir.get('status')} chain={row.get('status')}",
                )
            )
    for uetr in internal:
        if uetr not in chain:
            breaks.append(Break("MISSING_ON_CHAIN", uetr, "internal only"))
    # duplicates in internal
    with open(ledger_path, newline="", encoding="utf-8") as f:
        seen: set[str] = set()
        for r in csv.DictReader(f):
            u = r["uetr"]
            if u in seen:
                breaks.append(Break("DUPLICATE", u, "duplicate in internal ledger"))
            seen.add(u)
    return breaks
