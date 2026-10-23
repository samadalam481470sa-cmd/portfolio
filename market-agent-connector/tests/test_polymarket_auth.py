"""Tests for Polymarket CLOB auth headers."""

import base64

from market_agent.auth.polymarket_auth import build_clob_headers


def test_build_clob_headers():
    secret = base64.b64encode(b"test-secret-key-32bytes-long!!!!").decode()
    headers = build_clob_headers(
        api_key="test-key",
        secret=secret,
        passphrase="test-pass",
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        method="GET",
        path="/data/orders",
    )

    assert headers["POLY_API_KEY"] == "test-key"
    assert headers["POLY_PASSPHRASE"] == "test-pass"
    assert headers["POLY_ADDRESS"] == "0x1234567890abcdef1234567890abcdef12345678"
    assert "POLY_TIMESTAMP" in headers
    assert "POLY_SIGNATURE" in headers
