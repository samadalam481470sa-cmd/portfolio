"""OFF-CHAIN per-bank screening service (floats OK here)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rapidfuzz.distance import JaroWinkler
from rapidfuzz.fuzz import token_sort_ratio

from clearmesh.compliance.sanctions_list import SanctionsEntry, normalize_name
from clearmesh.crypto.keys import Ed25519Signer
from clearmesh.types.tx import Attestation, attestation_sign_bytes


class ScreenResult(StrEnum):
    HIT = "HIT"
    REVIEW = "REVIEW"
    CLEAR = "CLEAR"


@dataclass(frozen=True, slots=True)
class ScreenOutcome:
    result: ScreenResult
    score: float
    matched: str | None


def score_name(name: str, entries: list[SanctionsEntry]) -> ScreenOutcome:
    norm = normalize_name(name)
    best = 0.0
    matched: str | None = None
    for e in entries:
        candidates = [e.name, *e.aliases]
        for c in candidates:
            cn = normalize_name(c)
            jw = JaroWinkler.similarity(norm, cn)
            ts = token_sort_ratio(norm, cn) / 100.0
            sc = max(jw, ts)
            if sc > best:
                best = sc
                matched = c
    if best >= 0.90:
        return ScreenOutcome(ScreenResult.HIT, best, matched)
    if best >= 0.85:
        return ScreenOutcome(ScreenResult.REVIEW, best, matched)
    return ScreenOutcome(ScreenResult.CLEAR, best, matched)


def sign_attestation(
    signer: Ed25519Signer,
    chain_id: str,
    uetr: str,
    commitment: bytes,
    list_version: int,
    result: str,
    override_reason: str,
    screened_height: int,
    side: str,
) -> Attestation:
    from clearmesh.crypto.keys import key_id

    kid = key_id(signer.public_key)
    provisional = Attestation(
        uetr=uetr,
        commitment=commitment,
        list_version=list_version,
        result=result,
        override_reason=override_reason,
        screened_height=screened_height,
        side=side,
        key_id=kid,
        sig=b"\x00" * 64,
    )
    msg = attestation_sign_bytes(provisional, chain_id)
    sig = signer.sign(msg)
    return Attestation(
        uetr=uetr,
        commitment=commitment,
        list_version=list_version,
        result=result,
        override_reason=override_reason,
        screened_height=screened_height,
        side=side,
        key_id=kid,
        sig=sig,
    )
