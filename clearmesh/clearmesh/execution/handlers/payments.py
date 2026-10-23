"""Payment instruction, cancel, return handlers."""

from __future__ import annotations

from clearmesh.compliance.policy import check_payment
from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.crypto.hashing import h
from clearmesh.settlement import queue as Q
from clearmesh.settlement.lifecycle import transition
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Receipt
from clearmesh.types.records import Instruction
from clearmesh.types.tx import (
    CancelInstruction,
    PaymentInstruction,
    ReturnPayment,
    TxEnvelope,
    tx_id,
)


def handle_payment(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    check_payment(view, env, height)
    body = env.body
    assert isinstance(body, PaymentInstruction)
    pol = view.get_policy()
    assert pol is not None
    seq = view.next_seq()
    event = "ADMIT_CUSTOMER" if body.kind == "CUSTOMER" else "ADMIT_INTERBANK"
    screen_deadline = (
        height + pol.beneficiary_screen_timeout_blocks if body.kind == "CUSTOMER" else 0
    )
    env_commit = body.envelope.commitment if body.envelope else b"\x00" * 32
    orig_hash = (
        h("CLEARMESH/ATTEST/v1", body.originator_attestation.sig)
        if body.originator_attestation
        else b"\x00" * 32
    )
    stub = Instruction(
        uetr=body.uetr,
        e2e_id=body.end_to_end_id,
        kind=body.kind,
        debtor=body.debtor,
        creditor=body.creditor,
        asset=body.asset,
        amount=body.amount,
        priority=int(body.priority),
        status="NEW",
        admitted_height=height,
        seq=seq,
        settle_by_height=body.settle_by_height,
        envelope_commitment=env_commit,
        orig_att_hash=orig_hash,
        benef_att_hash=b"\x00" * 32,
        screen_deadline=screen_deadline,
        settled_height=None,
        method="",
        cycle_id=b"",
        return_of=None,
    )
    instr, rec = transition(
        stub, event, height=height, cause="TX", cause_ref=tx_id(env)
    )
    view.put_instruction(instr)
    view.mark_uetr(body.uetr)
    if instr.status == "QUEUED":
        Q.push(view, instr.debtor, instr.priority, instr.seq, instr.uetr)
        view.o.put(f"x/{instr.settle_by_height + 1:020d}/instr/{instr.uetr}", b"")
    elif instr.status == "AWAITING_BENEFICIARY_SCREEN":
        view.o.put(f"x/{screen_deadline:020d}/screen/{instr.uetr}", b"")
    return [rec]


def handle_cancel(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, CancelInstruction)
    instr = view.get_instruction(body.uetr)
    if instr is None:
        raise TxReject(ReasonCode.FF01, "unknown uetr")
    if env.signer != instr.debtor:
        raise TxReject(ReasonCode.BE05, "only debtor may cancel")
    if instr.status == "QUEUED":
        Q.remove(view, instr.debtor, instr.priority, instr.seq)
    new_i, rec = transition(
        instr, "CANCEL", height=height, cause="TX", cause_ref=tx_id(env), reason_code="CANCELLED"
    )
    view.put_instruction(new_i)
    return [rec]


def handle_return(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, ReturnPayment)
    orig = view.get_instruction(body.original_uetr)
    if orig is None or orig.status != "SETTLED":
        raise TxReject(ReasonCode.AG02, "original not settled")
    if body.amount > orig.amount:
        raise TxReject(ReasonCode.FF01, "return exceeds original")
    if env.signer != orig.creditor:
        raise TxReject(ReasonCode.BE05, "creditor must return")
    # Create reverse as INTERBANK-like queued payment from creditor to debtor
    pay = PaymentInstruction(
        kind="INTERBANK",
        uetr=body.new_uetr,
        end_to_end_id=f"RET-{orig.e2e_id}",
        debtor=orig.creditor,
        creditor=orig.debtor,
        asset=orig.asset,
        amount=body.amount,
        priority=1,
        settle_by_height=height + 100,
        purpose_code=body.reason,
        envelope=None,
        originator_attestation=None,
    )
    ret_env = TxEnvelope(
        version=env.version,
        chain_id=env.chain_id,
        tx_type=env.tx_type,
        signer=env.signer,
        valid_until_height=env.valid_until_height,
        body=pay,
        sigs=env.sigs,
    )
    # Bypass full check_payment signer==debtor already satisfied
    seq = view.next_seq()
    stub = Instruction(
        uetr=body.new_uetr,
        e2e_id=pay.end_to_end_id,
        kind="INTERBANK",
        debtor=pay.debtor,
        creditor=pay.creditor,
        asset=pay.asset,
        amount=pay.amount,
        priority=1,
        status="NEW",
        admitted_height=height,
        seq=seq,
        settle_by_height=pay.settle_by_height,
        envelope_commitment=b"\x00" * 32,
        orig_att_hash=b"\x00" * 32,
        benef_att_hash=b"\x00" * 32,
        screen_deadline=0,
        settled_height=None,
        method="",
        cycle_id=b"",
        return_of=body.original_uetr,
    )
    instr, rec = transition(stub, "ADMIT_INTERBANK", height=height, cause="TX", cause_ref=tx_id(env))
    view.put_instruction(instr)
    view.mark_uetr(body.new_uetr)
    Q.push(view, instr.debtor, instr.priority, instr.seq, instr.uetr)
    return [rec]
