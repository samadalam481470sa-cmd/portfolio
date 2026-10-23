"""Polymarket CLOB L2 HMAC authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time


def build_clob_headers(
    api_key: str,
    secret: str,
    passphrase: str,
    wallet_address: str,
    method: str,
    path: str,
    body: str = "",
) -> dict[str, str]:
    """Build POLY_* headers for CLOB L2 authenticated requests."""
    timestamp = str(int(time.time()))
    message = f"{timestamp}{method.upper()}{path}{body}"
    secret_bytes = base64.b64decode(secret)
    signature = base64.b64encode(
        hmac.new(secret_bytes, message.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    return {
        "POLY_ADDRESS": wallet_address,
        "POLY_API_KEY": api_key,
        "POLY_PASSPHRASE": passphrase,
        "POLY_TIMESTAMP": timestamp,
        "POLY_SIGNATURE": signature,
    }
