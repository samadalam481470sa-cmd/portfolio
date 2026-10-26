"""Recon breaks + travel-rule envelope isolation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from clearmesh.compliance.travel_rule import build_envelope, build_ivms101_subset, open_travel_envelope
from clearmesh.crypto.envelope import generate_enc_keypair
from clearmesh.recon.reconcile import reconcile_csv


def test_envelope_third_party_cannot_open() -> None:
    a_priv, a_pub = generate_enc_keypair()
    b_priv, b_pub = generate_enc_keypair()
    c_priv, c_pub = generate_enc_keypair()
    pt = build_ivms101_subset("Alice", "1", "x", "Bob", "2", "y")
    env = build_envelope(pt, "clearmesh-sim-1", "550e8400-e29b-41d4-a716-446655440000", [a_pub, b_pub])
    assert open_travel_envelope(env, "clearmesh-sim-1", "550e8400-e29b-41d4-a716-446655440000", a_priv)
    try:
        open_travel_envelope(env, "clearmesh-sim-1", "550e8400-e29b-41d4-a716-446655440000", c_priv)
        raised = False
    except Exception:
        raised = True
    assert raised


def test_recon_five_break_types() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.csv"
        ledger.write_text(
            "uetr,amount,status\n"
            "a,100,SETTLED\n"
            "b,200,SETTLED\n"
            "c,300,QUEUED\n"
            "d,400,SETTLED\n"
            "d,400,SETTLED\n"
            "e,500,SETTLED\n",
            encoding="utf-8",
        )
        chain = [
            {"uetr": "a", "amount": "100", "status": "SETTLED"},
            {"uetr": "b", "amount": "999", "status": "SETTLED"},  # amount mismatch
            {"uetr": "c", "amount": "300", "status": "SETTLED"},  # status mismatch
            {"uetr": "f", "amount": "1", "status": "SETTLED"},  # missing internally
            # e missing on chain
        ]
        breaks = reconcile_csv(ledger, chain)
        kinds = {b.kind for b in breaks}
        assert "AMOUNT_MISMATCH" in kinds
        assert "STATUS_MISMATCH" in kinds
        assert "MISSING_INTERNALLY" in kinds
        assert "MISSING_ON_CHAIN" in kinds
        assert "DUPLICATE" in kinds
