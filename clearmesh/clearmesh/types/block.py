"""Block, proposal, vote, and commit types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clearmesh.core.codec import encode
from clearmesh.crypto.hashing import h


@dataclass(frozen=True, slots=True)
class BlockHeader:
    version: int
    chain_id: str
    height: int
    round: int
    time_ms: int
    prev_block_hash: bytes
    last_commit_hash: bytes
    tx_root: bytes
    receipts_root: bytes
    state_root: bytes
    liabilities_root: bytes
    validators_hash: bytes
    policy_hash: bytes
    sanctions_version: int
    proposer_index: int


@dataclass(frozen=True, slots=True)
class CommitSig:
    validator_index: int
    sig: bytes


@dataclass(frozen=True, slots=True)
class Commit:
    height: int
    round: int
    block_hash: bytes
    sigs: tuple[CommitSig, ...]


@dataclass(frozen=True, slots=True)
class Block:
    header: BlockHeader
    txs: tuple[Any, ...]  # TxEnvelope
    last_commit: Commit | None


@dataclass(frozen=True, slots=True)
class Proposal:
    height: int
    round: int
    pol_round: int
    block: Block
    sig: bytes


@dataclass(frozen=True, slots=True)
class Vote:
    type: str  # PREVOTE | PRECOMMIT
    height: int
    round: int
    block_hash: bytes | None
    validator_index: int
    sig: bytes


def block_hash(header: BlockHeader) -> bytes:
    return h("CLEARMESH/HDR/v1", encode(header))


def vote_sign_bytes(chain_id: str, vote_type: str, height: int, round_: int, block_hash_: bytes | None) -> bytes:
    return h(
        "CLEARMESH/VOTE/v1",
        encode([chain_id, vote_type, height, round_, block_hash_ or b""]),
    )


def proposal_sign_bytes(chain_id: str, height: int, round_: int, pol_round: int, bh: bytes) -> bytes:
    return h(
        "CLEARMESH/PROPOSAL/v1",
        encode([chain_id, height, round_, pol_round, bh]),
    )
