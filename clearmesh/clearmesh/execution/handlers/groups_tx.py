"""Group propose/affirm handlers."""

from __future__ import annotations

from clearmesh.settlement.groups import affirm, propose
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Receipt
from clearmesh.types.tx import TxEnvelope, tx_id


def handle_propose_group(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    g = propose(view, env, height)
    return [
        Receipt(
            subject=g.group_id.hex(),
            from_status=None,
            to_status=g.status,
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]


def handle_affirm_group(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    g = affirm(view, env, height)
    return [
        Receipt(
            subject=g.group_id.hex(),
            from_status="PENDING",
            to_status=g.status,
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]
