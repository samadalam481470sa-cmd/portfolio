"""Transaction envelopes and bodies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Literal

from clearmesh.core.codec import encode
from clearmesh.crypto.hashing import h


class Priority(IntEnum):
    URGENT = 0
    NORMAL = 1


class Role(IntEnum):
    OPS = 1
    COMPLIANCE = 2
    GOV = 3
    SA = 4
    CSD = 5
    SCREENER = 6
    AUDITOR = 7
    VALIDATOR = 8


class TxType(IntEnum):
    REGISTER_PARTICIPANT = 1
    ROTATE_KEY = 2
    REVOKE_KEY = 3
    SET_POLICY = 4
    FREEZE_ACCOUNT = 5
    UNFREEZE_ACCOUNT = 6
    ISSUE = 7
    REDEEM = 8
    PUBLISH_SANCTIONS_LIST = 9
    PAYMENT_INSTRUCTION = 10
    BENEFICIARY_SCREEN_RESULT = 11
    CANCEL_INSTRUCTION = 12
    RETURN_PAYMENT = 13
    PROPOSE_GROUP = 14
    AFFIRM_GROUP = 15
    SET_DEBIT_CAP = 16
    EVIDENCE_EQUIVOCATION = 17


@dataclass(frozen=True, slots=True)
class Sig:
    key_id: bytes
    sig: bytes


@dataclass(frozen=True, slots=True)
class WrappedKey:
    recipient_key_id: bytes
    sealed_key: bytes


@dataclass(frozen=True, slots=True)
class Envelope:
    ciphertext: bytes
    wrapped_keys: tuple[WrappedKey, ...]
    commitment: bytes


@dataclass(frozen=True, slots=True)
class Attestation:
    uetr: str
    commitment: bytes
    list_version: int
    result: str  # CLEAR | OVERRIDE
    override_reason: str
    screened_height: int
    side: str  # ORIG | BENEF
    key_id: bytes
    sig: bytes


@dataclass(frozen=True, slots=True)
class PaymentInstruction:
    kind: str  # CUSTOMER | INTERBANK
    uetr: str
    end_to_end_id: str
    debtor: str
    creditor: str
    asset: str
    amount: int
    priority: int
    settle_by_height: int
    purpose_code: str
    envelope: Envelope | None
    originator_attestation: Attestation | None


@dataclass(frozen=True, slots=True)
class RegisterParticipant:
    participant_id: str
    lei: str
    display_name: str
    roles: tuple[int, ...]
    ops_pubkeys: tuple[bytes, ...]
    compliance_pubkeys: tuple[bytes, ...]
    enc_pubkey: bytes


@dataclass(frozen=True, slots=True)
class RotateKey:
    participant_id: str
    role: int
    new_pubkey: bytes


@dataclass(frozen=True, slots=True)
class RevokeKey:
    participant_id: str
    key_id: bytes


@dataclass(frozen=True, slots=True)
class SetPolicy:
    maker_checker_threshold: int
    netting_interval_blocks: int
    beneficiary_screen_timeout_blocks: int
    list_grace_blocks: int
    max_tx_per_block: int
    max_tx_ttl: int
    max_queue_units: int
    redeem_sa_threshold: int
    effective_height: int


@dataclass(frozen=True, slots=True)
class FreezeAccount:
    participant_id: str
    case_hash: bytes


@dataclass(frozen=True, slots=True)
class UnfreezeAccount:
    participant_id: str


@dataclass(frozen=True, slots=True)
class Issue:
    asset: str
    to: str
    amount: int


@dataclass(frozen=True, slots=True)
class Redeem:
    asset: str
    frm: str
    amount: int


@dataclass(frozen=True, slots=True)
class PublishSanctionsList:
    version: int
    merkle_root: bytes
    entry_count: int
    content_hash: bytes
    effective_height: int


@dataclass(frozen=True, slots=True)
class BeneficiaryScreenResult:
    uetr: str
    decision: str  # ACCEPT | REJECT
    reason: str
    list_version: int
    attestation: Attestation


@dataclass(frozen=True, slots=True)
class CancelInstruction:
    uetr: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReturnPayment:
    original_uetr: str
    new_uetr: str
    amount: int
    reason: str
    envelope: Envelope | None
    attestation: Attestation | None


@dataclass(frozen=True, slots=True)
class ProposeGroup:
    legs: tuple[tuple[str, str, str, int], ...]  # payer, payee, asset, amount
    priority: int
    expiry_height: int


@dataclass(frozen=True, slots=True)
class AffirmGroup:
    group_id: bytes


@dataclass(frozen=True, slots=True)
class SetDebitCap:
    asset: str
    cap: int


@dataclass(frozen=True, slots=True)
class EvidenceEquivocation:
    vote_a: bytes
    vote_b: bytes


TxBody = (
    RegisterParticipant
    | RotateKey
    | RevokeKey
    | SetPolicy
    | FreezeAccount
    | UnfreezeAccount
    | Issue
    | Redeem
    | PublishSanctionsList
    | PaymentInstruction
    | BeneficiaryScreenResult
    | CancelInstruction
    | ReturnPayment
    | ProposeGroup
    | AffirmGroup
    | SetDebitCap
    | EvidenceEquivocation
)


@dataclass(frozen=True, slots=True)
class TxEnvelope:
    version: int
    chain_id: str
    tx_type: int
    signer: str
    valid_until_height: int
    body: Any  # TxBody — kept Any for codec simplicity with tagged bodies
    sigs: tuple[Sig, ...]


def tx_sign_bytes(env: TxEnvelope) -> bytes:
    """Bytes covered by signatures (excludes sigs)."""
    return encode(
        [
            env.version,
            env.chain_id,
            int(env.tx_type),
            env.signer,
            env.valid_until_height,
            env.body,
        ]
    )


def tx_id(env: TxEnvelope) -> bytes:
    return h("CLEARMESH/TX/v1", tx_sign_bytes(env))


def attestation_sign_bytes(att: Attestation, chain_id: str) -> bytes:
    return h(
        "CLEARMESH/ATTEST/v1",
        encode(
            [
                chain_id,
                att.uetr,
                att.commitment,
                att.list_version,
                att.result,
                att.override_reason,
                att.screened_height,
                att.side,
                att.key_id,
            ]
        ),
    )
