"""Pure consensus validity rules for payments."""

from __future__ import annotations

from clearmesh.compliance.attestation import verify_attestation
from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.crypto.envelope import verify_commitment
from clearmesh.crypto.hashing import h
from clearmesh.crypto.keys import key_id, verify
from clearmesh.state.world import WorldView
from clearmesh.types.tx import (
    Envelope,
    PaymentInstruction,
    Role,
    TxEnvelope,
    WrappedKey,
    tx_id,
    tx_sign_bytes,
)


def _active_ops_keys(part, height: int) -> dict[bytes, bytes]:
    out: dict[bytes, bytes] = {}
    for kr in part.ops_keys:
        if kr.revoked_at is None or kr.revoked_at > height:
            out[kr.key_id] = kr.pubkey
    return out


def _active_compliance_keys(part, height: int) -> dict[bytes, bytes]:
    out: dict[bytes, bytes] = {}
    for kr in part.compliance_keys:
        if kr.revoked_at is None or kr.revoked_at > height:
            out[kr.key_id] = kr.pubkey
    return out


def verify_tx_sigs(view: WorldView, env: TxEnvelope, height: int, role: Role = Role.OPS) -> None:
    part = view.get_participant(env.signer)
    if part is None or not part.active:
        raise TxReject(ReasonCode.BE05, "unknown or inactive signer")
    keys = _active_ops_keys(part, height) if role == Role.OPS else _active_compliance_keys(part, height)
    if not env.sigs:
        raise TxReject(ReasonCode.DS0H, "missing signatures")
    seen: set[bytes] = set()
    msg = tx_sign_bytes(env)
    # Actually signatures are over tx_id digest
    digest = tx_id(env)
    for sig in env.sigs:
        if sig.key_id in seen:
            raise TxReject(ReasonCode.DS04, "duplicate key_id in sigs")
        seen.add(sig.key_id)
        pub = keys.get(sig.key_id)
        if pub is None:
            raise TxReject(ReasonCode.DS0H, "key not authorized or revoked")
        if not verify(pub, digest, sig.sig):
            raise TxReject(ReasonCode.DS0H, "bad signature")


def check_payment(view: WorldView, env: TxEnvelope, height: int) -> None:
    """Raise TxReject if PAYMENT_INSTRUCTION is invalid."""
    body = env.body
    if not isinstance(body, PaymentInstruction):
        raise TxReject(ReasonCode.FF01, "not a payment")
    if env.signer != body.debtor:
        raise TxReject(ReasonCode.BE05, "signer must be debtor")
    debtor = view.get_participant(body.debtor)
    creditor = view.get_participant(body.creditor)
    if debtor is None or not debtor.active:
        raise TxReject(ReasonCode.BE05, "debtor inactive")
    if Role.OPS not in debtor.roles and 1 not in debtor.roles:
        # roles stored as ints; OPS=1
        if 1 not in debtor.roles:
            raise TxReject(ReasonCode.AG01, "debtor is not a BANK with OPS")
    if creditor is None or not creditor.active:
        raise TxReject(ReasonCode.BE05, "creditor inactive")

    pol = view.get_policy()
    if pol is None:
        raise TxReject(ReasonCode.AG02, "no policy")

    # Maker-checker
    ops = _active_ops_keys(debtor, height)
    digest = tx_id(env)
    if not env.sigs:
        raise TxReject(ReasonCode.DS0H, "missing ops sigs")
    seen: set[bytes] = set()
    for sig in env.sigs:
        if sig.key_id in seen:
            raise TxReject(ReasonCode.DS04, "same ops key twice")
        seen.add(sig.key_id)
        pub = ops.get(sig.key_id)
        if pub is None:
            raise TxReject(ReasonCode.DS0H, "ops key not valid")
        if not verify(pub, digest, sig.sig):
            raise TxReject(ReasonCode.DS0H, "bad ops signature")
    if body.amount >= pol.maker_checker_threshold and len(seen) < 2:
        raise TxReject(ReasonCode.DS04, "maker-checker required")

    if view.uetr_seen(body.uetr):
        raise TxReject(ReasonCode.DUPL, "UETR reused")

    d_acct = view.get_account(body.debtor)
    c_acct = view.get_account(body.creditor)
    if d_acct is None or c_acct is None:
        raise TxReject(ReasonCode.FF01, "missing account")
    if d_acct.frozen or c_acct.frozen:
        raise TxReject(ReasonCode.AC06, "frozen account")

    if body.amount <= 0 or body.amount >= 2**63:
        raise TxReject(ReasonCode.FF01, "bad amount")

    if body.kind == "CUSTOMER":
        if body.envelope is None or body.originator_attestation is None:
            raise TxReject(ReasonCode.RR04, "customer payment needs envelope+attestation")
        envl: Envelope = body.envelope
        if not verify_commitment(envl):
            # Also accept types.tx.Envelope shaped the same
            from clearmesh.crypto.envelope import Envelope as CEnv
            from clearmesh.crypto.envelope import WrappedKey as CWK
            from clearmesh.crypto.envelope import verify_commitment as vc

            cenv = CEnv(
                ciphertext=envl.ciphertext,
                wrapped_keys=tuple(
                    CWK(w.recipient_key_id, w.sealed_key) for w in envl.wrapped_keys
                ),
                commitment=envl.commitment,
            )
            if not vc(cenv):
                raise TxReject(ReasonCode.RR04, "bad envelope commitment")

        # wrapped keys must include creditor enc + every auditor
        needed: set[bytes] = {key_id(creditor.enc_pubkey)}
        for k, _ in view.o.scan("part/"):
            pid = k.decode().split("/", 1)[1]
            p = view.get_participant(pid)
            if p and (Role.AUDITOR in p.roles or 7 in p.roles):
                needed.add(key_id(p.enc_pubkey))
        have = {w.recipient_key_id for w in envl.wrapped_keys}
        if not needed.issubset(have):
            raise TxReject(ReasonCode.RR04, "missing auditor or creditor wrap")

        att = body.originator_attestation
        if att.side != "ORIG" or att.uetr != body.uetr or att.commitment != envl.commitment:
            raise TxReject(ReasonCode.RR04, "attestation mismatch")
        comp = _active_compliance_keys(debtor, height)
        pub = comp.get(att.key_id)
        if pub is None:
            raise TxReject(ReasonCode.RR04, "compliance key revoked/missing")
        if not verify_attestation(att, env.chain_id, pub):
            raise TxReject(ReasonCode.RR04, "bad attestation signature")

        active_v = view.active_sanctions_version(height)
        if att.list_version != active_v:
            # grace for previous
            prev = att.list_version
            meta = view.get_sanctions(prev)
            active_meta = view.get_sanctions(active_v) if active_v else None
            ok = False
            if meta and active_meta and prev == active_v - 1:
                # superseded when active became effective
                if height <= active_meta.effective_height + pol.list_grace_blocks:
                    ok = True
            if not ok and att.list_version != active_v:
                raise TxReject(ReasonCode.RR04, "stale sanctions list")
        if att.screened_height > height:
            raise TxReject(ReasonCode.RR04, "screened in the future")

    elif body.kind == "INTERBANK":
        if body.envelope is not None or body.originator_attestation is not None:
            raise TxReject(ReasonCode.AG01, "interbank must not carry travel-rule data")
    else:
        raise TxReject(ReasonCode.FF01, "unknown payment kind")
