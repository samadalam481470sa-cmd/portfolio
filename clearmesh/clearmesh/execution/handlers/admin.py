"""Admin / governance handlers."""

from __future__ import annotations

from clearmesh.core.ids import validate_lei, validate_participant_id
from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.crypto.keys import key_id
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Receipt
from clearmesh.types.records import Account, KeyRec, Participant, Policy
from clearmesh.types.tx import (
    FreezeAccount,
    RegisterParticipant,
    RevokeKey,
    RotateKey,
    SetPolicy,
    TxEnvelope,
    UnfreezeAccount,
    tx_id,
)


def handle_register(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, RegisterParticipant)
    pid = validate_participant_id(body.participant_id)
    if view.get_participant(pid) is not None:
        raise TxReject(ReasonCode.DUPL, "participant exists")
    validate_lei(body.lei, check_mod97=False)  # synthetic LEIs may skip mod97 in demo
    ops = tuple(KeyRec(key_id=key_id(pk), pubkey=pk, revoked_at=None) for pk in body.ops_pubkeys)
    comp = tuple(
        KeyRec(key_id=key_id(pk), pubkey=pk, revoked_at=None) for pk in body.compliance_pubkeys
    )
    ops_ids = {k.key_id for k in ops}
    comp_ids = {k.key_id for k in comp}
    if ops_ids & comp_ids:
        raise TxReject(ReasonCode.AG01, "key cannot be both OPS and COMPLIANCE")
    p = Participant(
        id=pid,
        lei=body.lei,
        display_name=body.display_name,
        roles=body.roles,
        ops_keys=ops,
        compliance_keys=comp,
        enc_pubkey=body.enc_pubkey,
        active=True,
    )
    view.put_participant(p)
    view.put_account(pid, Account(frozen=False, freeze_case_hash=b"\x00" * 32, debit_caps=()))
    return [
        Receipt(
            subject=f"acct:{pid}",
            from_status=None,
            to_status="REGISTERED",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]


def handle_set_policy(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, SetPolicy)
    pol = Policy(
        maker_checker_threshold=body.maker_checker_threshold,
        netting_interval_blocks=body.netting_interval_blocks,
        beneficiary_screen_timeout_blocks=body.beneficiary_screen_timeout_blocks,
        list_grace_blocks=body.list_grace_blocks,
        max_tx_per_block=body.max_tx_per_block,
        max_tx_ttl=body.max_tx_ttl,
        max_queue_units=body.max_queue_units,
        redeem_sa_threshold=body.redeem_sa_threshold,
    )
    if body.effective_height <= height:
        view.put_policy(pol)
    else:
        from clearmesh.core.codec import encode

        view.o.put(f"pol_pending/{body.effective_height}", encode(pol))
    return [
        Receipt(
            subject="pol",
            from_status=None,
            to_status="POLICY_SET",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]


def handle_rotate(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, RotateKey)
    p = view.get_participant(body.participant_id)
    if p is None:
        raise TxReject(ReasonCode.FF01, "unknown participant")
    kid = key_id(body.new_pubkey)
    kr = KeyRec(key_id=kid, pubkey=body.new_pubkey, revoked_at=None)
    if body.role == 1:  # OPS
        view.put_participant(
            Participant(
                id=p.id,
                lei=p.lei,
                display_name=p.display_name,
                roles=p.roles,
                ops_keys=p.ops_keys + (kr,),
                compliance_keys=p.compliance_keys,
                enc_pubkey=p.enc_pubkey,
                active=p.active,
            )
        )
    elif body.role == 2:
        view.put_participant(
            Participant(
                id=p.id,
                lei=p.lei,
                display_name=p.display_name,
                roles=p.roles,
                ops_keys=p.ops_keys,
                compliance_keys=p.compliance_keys + (kr,),
                enc_pubkey=p.enc_pubkey,
                active=p.active,
            )
        )
    else:
        raise TxReject(ReasonCode.AG01, "unsupported role rotate")
    return [
        Receipt(
            subject=p.id,
            from_status=None,
            to_status="KEY_ROTATED",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]


def handle_revoke(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, RevokeKey)
    p = view.get_participant(body.participant_id)
    if p is None:
        raise TxReject(ReasonCode.FF01, "unknown participant")

    def rev(keys: tuple[KeyRec, ...]) -> tuple[KeyRec, ...]:
        out = []
        for k in keys:
            if k.key_id == body.key_id and k.revoked_at is None:
                out.append(KeyRec(key_id=k.key_id, pubkey=k.pubkey, revoked_at=height))
            else:
                out.append(k)
        return tuple(out)

    view.put_participant(
        Participant(
            id=p.id,
            lei=p.lei,
            display_name=p.display_name,
            roles=p.roles,
            ops_keys=rev(p.ops_keys),
            compliance_keys=rev(p.compliance_keys),
            enc_pubkey=p.enc_pubkey,
            active=p.active,
        )
    )
    return [
        Receipt(
            subject=p.id,
            from_status=None,
            to_status="KEY_REVOKED",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]


def handle_freeze(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, FreezeAccount)
    acct = view.get_account(body.participant_id)
    if acct is None:
        raise TxReject(ReasonCode.FF01, "no account")
    view.put_account(
        body.participant_id,
        Account(frozen=True, freeze_case_hash=body.case_hash, debit_caps=acct.debit_caps),
    )
    return [
        Receipt(
            subject=f"acct:{body.participant_id}",
            from_status="ACTIVE",
            to_status="FROZEN",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="AC06",
            postings=(),
        )
    ]


def handle_unfreeze(view: WorldView, env: TxEnvelope, height: int) -> list[Receipt]:
    body = env.body
    assert isinstance(body, UnfreezeAccount)
    acct = view.get_account(body.participant_id)
    if acct is None:
        raise TxReject(ReasonCode.FF01, "no account")
    view.put_account(
        body.participant_id,
        Account(frozen=False, freeze_case_hash=b"\x00" * 32, debit_caps=acct.debit_caps),
    )
    return [
        Receipt(
            subject=f"acct:{body.participant_id}",
            from_status="FROZEN",
            to_status="ACTIVE",
            height=height,
            cause="TX",
            cause_ref=tx_id(env),
            method="NONE",
            reason_code="OK",
            postings=(),
        )
    ]
