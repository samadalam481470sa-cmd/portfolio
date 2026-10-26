"""Equivocation evidence recording."""

from __future__ import annotations

import hashlib

from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Receipt
from clearmesh.types.tx import EvidenceEquivocation, TxEnvelope, tx_id


def handle_evidence(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, EvidenceEquivocation)
    digest = hashlib.sha256(body.vote_a + body.vote_b).digest()
    view.o.put(f"evid/{digest.hex()}", body.vote_a + b"|" + body.vote_b)
    return [
        Receipt(
            subject=digest.hex(),
            from_status=None,
            to_status="EVIDENCE",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]
