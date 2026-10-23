"""DuplicateVoteEvidence build/verify."""

from __future__ import annotations

from clearmesh.core.codec import encode
from clearmesh.crypto.keys import verify
from clearmesh.types.block import Vote, vote_sign_bytes
from clearmesh.types.tx import EvidenceEquivocation


def build_equivocation(vote_a: Vote, vote_b: Vote) -> EvidenceEquivocation:
    return EvidenceEquivocation(vote_a=encode(vote_a), vote_b=encode(vote_b))


def verify_equivocation(
    chain_id: str,
    vote_a: Vote,
    vote_b: Vote,
    pubkey: bytes,
) -> bool:
    if vote_a.validator_index != vote_b.validator_index:
        return False
    if (vote_a.height, vote_a.round, vote_a.type) != (vote_b.height, vote_b.round, vote_b.type):
        return False
    if vote_a.block_hash == vote_b.block_hash:
        return False
    for v in (vote_a, vote_b):
        msg = vote_sign_bytes(chain_id, v.type, v.height, v.round, v.block_hash)
        if not verify(pubkey, msg, v.sig):
            return False
    return True
