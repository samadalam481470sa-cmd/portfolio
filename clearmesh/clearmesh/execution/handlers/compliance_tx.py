"""Sanctions publish and beneficiary screen result handlers."""

from __future__ import annotations

from clearmesh.compliance.attestation import verify_attestation
from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.crypto.hashing import h
from clearmesh.settlement import queue as Q
from clearmesh.settlement.lifecycle import transition
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Receipt
from clearmesh.types.records import SanctionsListMeta
from clearmesh.types.tx import BeneficiaryScreenResult, PublishSanctionsList, TxEnvelope, tx_id


def handle_publish_sanctions(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, PublishSanctionsList)
    if view.get_sanctions(body.version) is not None:
        raise TxReject(ReasonCode.DUPL, "list version exists")
    meta = SanctionsListMeta(
        version=body.version,
        merkle_root=body.merkle_root,
        entry_count=body.entry_count,
        content_hash=body.content_hash,
        effective_height=body.effective_height,
    )
    view.put_sanctions(meta)
    return [
        Receipt(
            subject=f"sanc:{body.version}",
            from_status=None,
            to_status="PUBLISHED",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]


def handle_benef_screen(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, BeneficiaryScreenResult)
    instr = view.get_instruction(body.uetr)
    if instr is None:
        raise TxReject(ReasonCode.FF01, "unknown uetr")
    if instr.status != "AWAITING_BENEFICIARY_SCREEN":
        raise TxReject(ReasonCode.AG02, "not awaiting screen")
    if env.signer != instr.creditor:
        raise TxReject(ReasonCode.BE05, "creditor compliance only")
    creditor = view.get_participant(instr.creditor)
    assert creditor is not None
    att = body.attestation
    if att.side != "BENEF" or att.uetr != body.uetr:
        raise TxReject(ReasonCode.RR04, "bad benef attestation")
    if att.commitment != instr.envelope_commitment:
        raise TxReject(ReasonCode.RR04, "commitment mismatch")
    pub = None
    for kr in creditor.compliance_keys:
        if kr.key_id == att.key_id and (kr.revoked_at is None or kr.revoked_at > height):
            pub = kr.pubkey
            break
    if pub is None or not verify_attestation(att, env.chain_id, pub):
        raise TxReject(ReasonCode.RR04, "bad benef attestation sig")

    if body.decision == "ACCEPT":
        new_i, rec = transition(instr, "ACCEPT", height=height, cause="TX", cause_ref=tx_id(env))
        from dataclasses import replace

        new_i = replace(new_i, benef_att_hash=h("CLEARMESH/ATTEST/v1", att.sig))
        view.put_instruction(new_i)
        Q.push(view, new_i.debtor, new_i.priority, new_i.seq, new_i.uetr)
        view.o.put(f"x/{new_i.settle_by_height + 1:020d}/instr/{new_i.uetr}", b"")
        return [rec]
    if body.decision == "REJECT":
        new_i, rec = transition(
            instr,
            "REJECT",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            reason_code=body.reason or "RR04",
        )
        view.put_instruction(new_i)
        return [rec]
    raise TxReject(ReasonCode.FF01, "bad decision")
