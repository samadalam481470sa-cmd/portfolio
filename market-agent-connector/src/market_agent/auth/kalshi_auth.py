"""Kalshi RSA-PSS request signing."""

from __future__ import annotations

import base64
import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def load_private_key(pem: str):
    return serialization.load_pem_private_key(
        pem.encode("utf-8") if isinstance(pem, str) else pem,
        password=None,
        backend=default_backend(),
    )


def sign_request(private_key_pem: str, method: str, path: str) -> dict[str, str]:
    """Return Kalshi auth headers for a signed request."""
    timestamp = str(int(time.time() * 1000))
    path_without_query = path.split("?")[0]
    message = f"{timestamp}{method.upper()}{path_without_query}"

    private_key = load_private_key(private_key_pem)
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )

    return {
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
    }
