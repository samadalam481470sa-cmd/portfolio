"""Multi-recipient travel-rule envelope (XChaCha20-Poly1305 + SealedBox)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.bindings import (
    crypto_aead_xchacha20poly1305_ietf_decrypt,
    crypto_aead_xchacha20poly1305_ietf_encrypt,
)

import cbor2

from clearmesh.crypto.hashing import h
from clearmesh.crypto.keys import key_id


@dataclass(frozen=True, slots=True)
class WrappedKey:
    recipient_key_id: bytes
    sealed_key: bytes


@dataclass(frozen=True, slots=True)
class Envelope:
    ciphertext: bytes
    wrapped_keys: tuple[WrappedKey, ...]
    commitment: bytes


def _commitment_bytes(ciphertext: bytes, wrapped_keys: tuple[WrappedKey, ...]) -> bytes:
    payload = [
        ciphertext,
        [[wk.recipient_key_id, wk.sealed_key] for wk in wrapped_keys],
    ]
    return h("CLEARMESH/ENV/v1", cbor2.dumps(payload, canonical=True))


def seal(
    plaintext: bytes,
    recipients: list[tuple[bytes, bytes]],
    aad: bytes,
) -> Envelope:
    """Encrypt plaintext to recipients. recipients = [(key_id, x25519_pub), ...]."""
    if not recipients:
        raise ValueError("at least one recipient required")
    seen: set[bytes] = set()
    for kid, pub in recipients:
        if kid in seen:
            raise ValueError("duplicate recipient key_id")
        seen.add(kid)
        if len(pub) != 32 or len(kid) != 20:
            raise ValueError("invalid recipient key material")

    data_key = os.urandom(32)
    nonce = os.urandom(24)
    ct_body = crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, data_key)
    ciphertext = nonce + ct_body

    wrapped: list[WrappedKey] = []
    for kid, pub in sorted(recipients, key=lambda x: x[0]):
        box = SealedBox(PublicKey(pub))
        sealed = box.encrypt(data_key)
        wrapped.append(WrappedKey(recipient_key_id=kid, sealed_key=bytes(sealed)))

    wk = tuple(wrapped)
    commitment = _commitment_bytes(ciphertext, wk)
    return Envelope(ciphertext=ciphertext, wrapped_keys=wk, commitment=commitment)


def open_envelope(env: Envelope, kid: bytes, x25519_priv: bytes, aad: bytes) -> bytes:
    """Decrypt envelope for the given recipient private key."""
    if len(x25519_priv) != 32:
        raise ValueError("invalid private key")
    match = None
    for wk in env.wrapped_keys:
        if wk.recipient_key_id == kid:
            match = wk
            break
    if match is None:
        raise ValueError("recipient not present")
    try:
        sk = PrivateKey(x25519_priv)
        data_key = SealedBox(sk).decrypt(match.sealed_key)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("failed to unwrap data key") from exc
    if len(env.ciphertext) < 24:
        raise ValueError("ciphertext too short")
    nonce, body = env.ciphertext[:24], env.ciphertext[24:]
    try:
        return crypto_aead_xchacha20poly1305_ietf_decrypt(body, aad, nonce, data_key)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("AEAD decrypt failed") from exc


def verify_commitment(env: Envelope) -> bool:
    return _commitment_bytes(env.ciphertext, env.wrapped_keys) == env.commitment


def enc_key_id(x25519_pub: bytes) -> bytes:
    return key_id(x25519_pub)


def generate_enc_keypair() -> tuple[bytes, bytes]:
    """Return (private, public) X25519 keypair."""
    sk = PrivateKey.generate()
    return bytes(sk), bytes(sk.public_key)
