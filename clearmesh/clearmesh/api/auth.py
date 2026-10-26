"""Signed-request auth for participant endpoints."""

from __future__ import annotations

import hashlib
import hmac
import time

from clearmesh.crypto.hashing import h
from clearmesh.crypto.keys import verify


def rpc_sign_bytes(method: str, path: str, query: str, ts_ms: int, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).digest()
    return h(
        "CLEARMESH/RPC/v1",
        method.encode() + path.encode() + query.encode() + ts_ms.to_bytes(8, "big") + body_hash,
    )


def verify_request(
    pubkey: bytes,
    sig: bytes,
    method: str,
    path: str,
    query: str,
    ts_ms: int,
    body: bytes,
    now_ms: int | None = None,
) -> bool:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    if abs(now - ts_ms) > 30_000:
        return False
    msg = rpc_sign_bytes(method, path, query, ts_ms, body)
    if not verify(pubkey, msg, sig):
        return False
    return True


def constant_time_eq(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)
