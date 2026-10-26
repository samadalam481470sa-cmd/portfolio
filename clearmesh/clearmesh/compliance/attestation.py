"""Attestation sign/verify helpers."""

from __future__ import annotations

from clearmesh.crypto.keys import verify
from clearmesh.types.tx import Attestation, attestation_sign_bytes


def verify_attestation(att: Attestation, chain_id: str, pubkey: bytes) -> bool:
    if att.result not in ("CLEAR", "OVERRIDE"):
        return False
    if att.side not in ("ORIG", "BENEF"):
        return False
    msg = attestation_sign_bytes(att, chain_id)
    # sig is over the domain-separated hash already returned by attestation_sign_bytes
    # Actually attestation_sign_bytes returns h(ATTEST, encode(...)) — sign that digest
    return verify(pubkey, msg, att.sig)
