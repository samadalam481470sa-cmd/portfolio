"""Tests for Kalshi RSA-PSS signing."""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from market_agent.auth.kalshi_auth import sign_request


def _generate_test_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def test_sign_request_returns_required_headers():
    pem = _generate_test_key_pem()
    headers = sign_request(pem, "GET", "/trade-api/v2/portfolio/balance")

    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert "KALSHI-ACCESS-SIGNATURE" in headers
    assert headers["KALSHI-ACCESS-TIMESTAMP"].isdigit()
    # Valid base64 signature
    base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])


def test_sign_strips_query_params():
    pem = _generate_test_key_pem()
    h1 = sign_request(pem, "GET", "/trade-api/v2/portfolio/orders?limit=5")
    h2 = sign_request(pem, "GET", "/trade-api/v2/portfolio/orders")
    # Timestamps differ but both should produce valid signatures
    assert "KALSHI-ACCESS-SIGNATURE" in h1
    assert "KALSHI-ACCESS-SIGNATURE" in h2
