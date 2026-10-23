"""Dispatch transaction bodies to handlers."""

from __future__ import annotations

from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.execution.handlers import admin, compliance_tx, evidence, groups_tx, money, payments
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Receipt
from clearmesh.types.tx import TxEnvelope, TxType


def handle_tx(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    t = TxType(env.tx_type)
    if t == TxType.REGISTER_PARTICIPANT:
        return admin.handle_register(view, env, height)
    if t == TxType.ROTATE_KEY:
        return admin.handle_rotate(view, env, height)
    if t == TxType.REVOKE_KEY:
        return admin.handle_revoke(view, env, height)
    if t == TxType.SET_POLICY:
        return admin.handle_set_policy(view, env, height)
    if t == TxType.FREEZE_ACCOUNT:
        return admin.handle_freeze(view, env, height)
    if t == TxType.UNFREEZE_ACCOUNT:
        return admin.handle_unfreeze(view, env, height)
    if t == TxType.ISSUE:
        return money.handle_issue(view, env, height)
    if t == TxType.REDEEM:
        return money.handle_redeem(view, env, height)
    if t == TxType.SET_DEBIT_CAP:
        return money.handle_debit_cap(view, env, height)
    if t == TxType.PUBLISH_SANCTIONS_LIST:
        return compliance_tx.handle_publish_sanctions(view, env, height)
    if t == TxType.PAYMENT_INSTRUCTION:
        return payments.handle_payment(view, env, height)
    if t == TxType.BENEFICIARY_SCREEN_RESULT:
        return compliance_tx.handle_benef_screen(view, env, height)
    if t == TxType.CANCEL_INSTRUCTION:
        return payments.handle_cancel(view, env, height)
    if t == TxType.RETURN_PAYMENT:
        return payments.handle_return(view, env, height)
    if t == TxType.PROPOSE_GROUP:
        return groups_tx.handle_propose_group(view, env, height)
    if t == TxType.AFFIRM_GROUP:
        return groups_tx.handle_affirm_group(view, env, height)
    if t == TxType.EVIDENCE_EQUIVOCATION:
        return evidence.handle_evidence(view, env, height)
    raise TxReject(ReasonCode.FF01, f"unknown tx type {env.tx_type}")
