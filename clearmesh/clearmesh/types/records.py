"""On-chain state records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class InstrStatus(StrEnum):
    AWAITING_BENEFICIARY_SCREEN = "AWAITING_BENEFICIARY_SCREEN"
    QUEUED = "QUEUED"
    SETTLED = "SETTLED"
    REJECTED_BENEFICIARY = "REJECTED_BENEFICIARY"
    BENEFICIARY_TIMEOUT = "BENEFICIARY_TIMEOUT"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class GroupStatus(StrEnum):
    PENDING = "PENDING"
    ARMED = "ARMED"
    SETTLED = "SETTLED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class KeyRec:
    key_id: bytes
    pubkey: bytes
    revoked_at: int | None


@dataclass(frozen=True, slots=True)
class Participant:
    id: str
    lei: str
    display_name: str
    roles: tuple[int, ...]
    ops_keys: tuple[KeyRec, ...]
    compliance_keys: tuple[KeyRec, ...]
    enc_pubkey: bytes
    active: bool


@dataclass(frozen=True, slots=True)
class Account:
    frozen: bool
    freeze_case_hash: bytes
    debit_caps: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class AssetMeta:
    decimals: int
    issuer_role: int
    total_supply: int


@dataclass(frozen=True, slots=True)
class Instruction:
    uetr: str
    e2e_id: str
    kind: str
    debtor: str
    creditor: str
    asset: str
    amount: int
    priority: int
    status: str
    admitted_height: int
    seq: int
    settle_by_height: int
    envelope_commitment: bytes
    orig_att_hash: bytes
    benef_att_hash: bytes
    screen_deadline: int
    settled_height: int | None
    method: str
    cycle_id: bytes
    return_of: str | None


@dataclass(frozen=True, slots=True)
class Leg:
    payer: str
    payee: str
    asset: str
    amount: int


@dataclass(frozen=True, slots=True)
class Group:
    group_id: bytes
    legs: tuple[Leg, ...]
    required: tuple[str, ...]
    affirmed: tuple[str, ...]
    status: str
    priority: int
    admitted_height: int
    seq: int
    expiry_height: int


@dataclass(frozen=True, slots=True)
class Policy:
    maker_checker_threshold: int
    netting_interval_blocks: int
    beneficiary_screen_timeout_blocks: int
    list_grace_blocks: int
    max_tx_per_block: int
    max_tx_ttl: int
    max_queue_units: int
    redeem_sa_threshold: int


@dataclass(frozen=True, slots=True)
class SanctionsListMeta:
    version: int
    merkle_root: bytes
    entry_count: int
    content_hash: bytes
    effective_height: int


@dataclass(frozen=True, slots=True)
class AssetStat:
    asset: str
    gross: int
    liquidity_used: int
    lsr_bps: int


@dataclass(frozen=True, slots=True)
class NettingReport:
    cycle_id: bytes
    height: int
    settled: tuple[bytes, ...]
    deferred: tuple[bytes, ...]
    per_asset: tuple[AssetStat, ...]


class Priority(IntEnum):
    URGENT = 0
    NORMAL = 1
