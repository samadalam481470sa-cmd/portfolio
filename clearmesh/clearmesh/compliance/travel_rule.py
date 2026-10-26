"""IVMS101 subset travel-rule envelope build/open."""

from __future__ import annotations

import json
from typing import Any

from clearmesh.crypto.envelope import Envelope, generate_enc_keypair, open_envelope, seal
from clearmesh.crypto.keys import key_id


def build_ivms101_subset(
    originator_name: str,
    originator_account: str,
    originator_address: str,
    beneficiary_name: str,
    beneficiary_account: str,
    beneficiary_address: str,
) -> bytes:
    doc: dict[str, Any] = {
        "Originator": {
            "name": originator_name,
            "account": originator_account,
            "address": originator_address,
        },
        "Beneficiary": {
            "name": beneficiary_name,
            "account": beneficiary_account,
            "address": beneficiary_address,
        },
        "schema": "IVMS101-subset-clearmesh-1",
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_envelope(
    plaintext: bytes,
    chain_id: str,
    uetr: str,
    recipient_pubs: list[bytes],
) -> Envelope:
    aad = chain_id.encode("ascii") + uetr.encode("ascii")
    recipients = [(key_id(pub), pub) for pub in recipient_pubs]
    return seal(plaintext, recipients, aad)


def open_travel_envelope(
    env: Envelope,
    chain_id: str,
    uetr: str,
    x25519_priv: bytes,
) -> bytes:
    aad = chain_id.encode("ascii") + uetr.encode("ascii")
    from nacl.public import PrivateKey

    pub = bytes(PrivateKey(x25519_priv).public_key)
    return open_envelope(env, key_id(pub), x25519_priv, aad)


__all__ = [
    "build_envelope",
    "build_ivms101_subset",
    "generate_enc_keypair",
    "open_travel_envelope",
]
