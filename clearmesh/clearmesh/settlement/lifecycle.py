"""Instruction status transitions."""

from __future__ import annotations

from dataclasses import replace

from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.types.receipt import Receipt
from clearmesh.types.records import Instruction

TRANSITIONS: dict[tuple[str | None, str], str] = {
    (None, "ADMIT_CUSTOMER"): "AWAITING_BENEFICIARY_SCREEN",
    (None, "ADMIT_INTERBANK"): "QUEUED",
    ("AWAITING_BENEFICIARY_SCREEN", "ACCEPT"): "QUEUED",
    ("AWAITING_BENEFICIARY_SCREEN", "REJECT"): "REJECTED_BENEFICIARY",
    ("AWAITING_BENEFICIARY_SCREEN", "TIMEOUT"): "BENEFICIARY_TIMEOUT",
    ("AWAITING_BENEFICIARY_SCREEN", "CANCEL"): "CANCELLED",
    ("QUEUED", "CANCEL"): "CANCELLED",
    ("QUEUED", "SETTLE"): "SETTLED",
    ("QUEUED", "EXPIRE"): "EXPIRED",
}

TERMINAL = frozenset(
    {
        "SETTLED",
        "CANCELLED",
        "EXPIRED",
        "REJECTED_BENEFICIARY",
        "BENEFICIARY_TIMEOUT",
    }
)


def transition(
    instr: Instruction,
    event: str,
    *,
    height: int,
    cause: str,
    cause_ref: bytes,
    method: str = "NONE",
    reason_code: str = "OK",
    postings: tuple = (),
) -> tuple[Instruction, Receipt]:
    frm = None if event.startswith("ADMIT_") else instr.status
    key = (frm, event)
    if key not in TRANSITIONS:
        raise TxReject(ReasonCode.AG02, f"illegal transition {frm} + {event}")
    to = TRANSITIONS[key]
    reason = reason_code
    if event == "TIMEOUT":
        reason = ReasonCode.AB05.value
    elif event == "EXPIRE":
        reason = ReasonCode.AM04.value
    new = replace(
        instr,
        status=to,
        settled_height=height if to == "SETTLED" else instr.settled_height,
        method=method if to == "SETTLED" else instr.method,
    )
    receipt = Receipt(
        subject=instr.uetr,
        from_status=frm,
        to_status=to,
        height=height,
        cause=cause,
        cause_ref=cause_ref,
        method=method,
        reason_code=reason,
        postings=tuple(postings),
    )
    return new, receipt
