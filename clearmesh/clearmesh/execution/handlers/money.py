"""Issue / redeem / debit-cap handlers."""

from __future__ import annotations

from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.ledger.journal import issue, redeem
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Receipt
from clearmesh.types.records import Account
from clearmesh.types.tx import Issue, Redeem, SetDebitCap, TxEnvelope, TxType, tx_id


def handle_issue(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, Issue)
    meta = view.get_asset(body.asset)
    if meta is None:
        raise TxReject(ReasonCode.FF01, "unknown asset")
    part = view.get_participant(env.signer)
    if part is None or meta.issuer_role not in part.roles:
        raise TxReject(ReasonCode.DS0H, "issuer role required")
    entries = issue(view, body.asset, body.to, body.amount)
    return [
        Receipt(
            subject=f"acct:{body.to}",
            from_status=None,
            to_status="ISSUED",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=tuple(entries),
        )
    ]


def handle_redeem(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, Redeem)
    entries = redeem(view, body.asset, body.frm, body.amount)
    return [
        Receipt(
            subject=f"acct:{body.frm}",
            from_status=None,
            to_status="REDEEMED",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=tuple(entries),
        )
    ]


def handle_debit_cap(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, SetDebitCap)
    if env.signer != env.signer:
        raise TxReject(ReasonCode.BE05, "own ops only")
    acct = view.get_account(env.signer)
    if acct is None:
        raise TxReject(ReasonCode.FF01, "no account")
    caps = dict(acct.debit_caps)
    caps[body.asset] = body.cap
    new_caps = tuple(sorted(caps.items()))
    view.put_account(
        env.signer,
        Account(frozen=acct.frozen, freeze_case_hash=acct.freeze_case_hash, debit_caps=new_caps),
    )
    return [
        Receipt(
            subject=f"acct:{env.signer}",
            from_status=None,
            to_status="DEBIT_CAP",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]
