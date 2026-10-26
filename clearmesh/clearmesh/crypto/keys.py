"""Ed25519 signing via PyNaCl / libsodium only."""

from __future__ import annotations

from typing import Protocol

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from clearmesh.crypto.hashing import h

PUBKEY_LEN = 32
SIG_LEN = 64
SEED_LEN = 32


class Signer(Protocol):
    def sign(self, msg: bytes) -> bytes: ...

    @property
    def public_key(self) -> bytes: ...


def key_id(pubkey: bytes) -> bytes:
    if len(pubkey) != PUBKEY_LEN:
        raise ValueError("pubkey must be 32 bytes")
    return h("CLEARMESH/LEAF/v1", pubkey)[:20]


class Ed25519Signer:
    __slots__ = ("_sk",)

    def __init__(self, seed: bytes | None = None) -> None:
        if seed is None:
            self._sk = SigningKey.generate()
        else:
            if len(seed) != SEED_LEN:
                raise ValueError("seed must be 32 bytes")
            self._sk = SigningKey(seed)

    @property
    def public_key(self) -> bytes:
        return bytes(self._sk.verify_key)

    @property
    def seed(self) -> bytes:
        return bytes(self._sk)

    def sign(self, msg: bytes) -> bytes:
        if not isinstance(msg, (bytes, bytearray)):
            raise TypeError("msg must be bytes")
        sig = self._sk.sign(bytes(msg)).signature
        if len(sig) != SIG_LEN:
            raise RuntimeError("unexpected signature length")
        return bytes(sig)


def verify(pubkey: bytes, msg: bytes, sig: bytes) -> bool:
    if len(pubkey) != PUBKEY_LEN or len(sig) != SIG_LEN:
        return False
    if not isinstance(msg, (bytes, bytearray)):
        return False
    try:
        VerifyKey(pubkey).verify(bytes(msg), bytes(sig))
        return True
    except BadSignatureError:
        return False
    except Exception:  # noqa: BLE001
        return False
