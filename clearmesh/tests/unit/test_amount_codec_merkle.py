"""Phase 0 foundation tests."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from clearmesh.core.amount import Amount, AmountError
from clearmesh.core.codec import CodecError, decode, encode
from clearmesh.crypto.keys import Ed25519Signer, verify
from clearmesh.crypto.merkle import inclusion_proof, merkle_root, verify_inclusion
from clearmesh.crypto.sumtree import sum_proof, sumtree_root, verify_sum
from clearmesh.types.receipt import Posting


def test_amount_parse_basic() -> None:
    assert Amount.parse("1250.00", 2).value == 125000
    assert Amount.parse("10", 2).value == 1000


def test_amount_rejects() -> None:
    with pytest.raises(AmountError):
        Amount.parse("0", 2)
    with pytest.raises(AmountError):
        Amount.parse("-1.00", 2)
    with pytest.raises(AmountError):
        Amount.parse("1.005", 2)
    with pytest.raises(AmountError):
        Amount(2**63)


def test_rfc8032_sign_verify() -> None:
    # Deterministic seed
    sk = Ed25519Signer(b"\x01" * 32)
    msg = b"clearmesh-test"
    sig = sk.sign(msg)
    assert verify(sk.public_key, msg, sig)
    assert not verify(sk.public_key, msg, b"\x00" * 64)


def test_merkle_proofs_1_to_33() -> None:
    for n in range(1, 34):
        leaves = [f"leaf-{i}".encode() for i in range(n)]
        root = merkle_root(leaves)
        for i in range(n):
            proof = inclusion_proof(leaves, i)
            assert verify_inclusion(root, leaves[i], i, n, proof)
            bad = bytearray(leaves[i])
            bad[0] ^= 1
            assert not verify_inclusion(root, bytes(bad), i, n, proof)


def test_sumtree_rejects_tamper() -> None:
    leaves = [("BANKA", 100), ("BANKB", 200), ("BANKC", 300)]
    root, total = sumtree_root(leaves)
    assert total == 600
    proof = sum_proof(leaves, 1)
    assert verify_sum(root, "BANKB", 200, 1, 3, proof, 600)
    assert not verify_sum(root, "BANKB", 201, 1, 3, proof, 600)


def test_codec_roundtrip_posting() -> None:
    p = Posting(account="BANKA", asset="SIM", delta=100)
    raw = encode(p)
    assert decode(Posting, raw) == p


@given(st.integers(min_value=1, max_value=2**31))
def test_codec_int_roundtrip(n: int) -> None:
    raw = encode(n)
    assert decode(int, raw) == n  # type: ignore[arg-type]


def test_noncanonical_rejected() -> None:
    p = Posting(account="BANKA", asset="SIM", delta=1)
    raw = encode(p)
    with pytest.raises(CodecError):
        decode(Posting, raw + b"\x00")
