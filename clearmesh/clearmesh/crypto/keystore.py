"""Argon2id + SecretBox encrypted key files."""

from __future__ import annotations

import json
import os
from pathlib import Path

from nacl.pwhash import argon2id
from nacl.secret import SecretBox
from nacl.utils import random

OPS_LIMIT = argon2id.OPSLIMIT_MODERATE
MEM_LIMIT = argon2id.MEMLIMIT_MODERATE


def encrypt_seed(seed: bytes, password: str) -> dict[str, str]:
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    salt = random(argon2id.SALTBYTES)
    key = argon2id.kdf(SecretBox.KEY_SIZE, password.encode("utf-8"), salt, OPS_LIMIT, MEM_LIMIT)
    box = SecretBox(key)
    nonce = random(SecretBox.NONCE_SIZE)
    ct = box.encrypt(seed, nonce)
    return {
        "kdf": "argon2id",
        "ops": str(OPS_LIMIT),
        "mem": str(MEM_LIMIT),
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "ciphertext": bytes(ct).hex(),
    }


def decrypt_seed(blob: dict[str, str], password: str) -> bytes:
    salt = bytes.fromhex(blob["salt"])
    nonce = bytes.fromhex(blob["nonce"])
    ct = bytes.fromhex(blob["ciphertext"])
    ops = int(blob.get("ops", OPS_LIMIT))
    mem = int(blob.get("mem", MEM_LIMIT))
    key = argon2id.kdf(SecretBox.KEY_SIZE, password.encode("utf-8"), salt, ops, mem)
    box = SecretBox(key)
    # SecretBox.encrypt includes nonce prefix in ct; handle both forms
    try:
        return box.decrypt(ct)
    except Exception:
        return box.decrypt(ct[SecretBox.NONCE_SIZE :], nonce)


def save_keystore(path: Path | str, seed: bytes, password: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = encrypt_seed(seed, password)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_keystore(path: Path | str, password: str) -> bytes:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return decrypt_seed(data, password)
