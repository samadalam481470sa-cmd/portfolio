"""Range fetch, verify commit, re-execute, apply."""

from __future__ import annotations

from clearmesh.core.codec import encode
from clearmesh.crypto.keys import verify
from clearmesh.execution.executor import apply_block
from clearmesh.state.overlay import Overlay
from clearmesh.state.store import Store
from clearmesh.types.block import Block, Commit, block_hash, vote_sign_bytes


def verify_and_apply(
    store: Store,
    block: Block,
    commit: Commit,
    chain_id: str,
    validator_pubs: list[bytes],
    min_sigs: int = 3,
) -> None:
    bh = block_hash(block.header)
    if commit.block_hash != bh:
        raise ValueError("commit hash mismatch")
    need = 1 if len(validator_pubs) == 1 else min_sigs
    if len(commit.sigs) < need:
        raise ValueError("insufficient commit sigs")
    for cs in commit.sigs:
        if cs.validator_index < 0 or cs.validator_index >= len(validator_pubs):
            raise ValueError("bad validator index")
        pub = validator_pubs[cs.validator_index]
        msg = vote_sign_bytes(chain_id, "PRECOMMIT", commit.height, commit.round, bh)
        if not verify(pub, msg, cs.sig):
            raise ValueError("bad commit sig")
    overlay = Overlay(store)
    result = apply_block(overlay, block, chain_id)
    if result.roots["state_root"] != block.header.state_root:
        raise ValueError("state_root mismatch")
    if result.roots["receipts_root"] != block.header.receipts_root:
        raise ValueError("receipts_root mismatch")
    if result.roots["liabilities_root"] != block.header.liabilities_root:
        raise ValueError("liabilities_root mismatch")
    store.commit_block(
        height=block.header.height,
        block_bytes=encode(block),
        commit_bytes=encode(commit),
        receipts_bytes=encode(result.receipts),
        roots=result.roots,
        writes=result.writes,
        tx_ids=result.tx_ids,
    )
