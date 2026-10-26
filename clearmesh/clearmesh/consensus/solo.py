"""Single-node sequencer implementing ConsensusEngine (phases 1–3 / demo fallback)."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from clearmesh.core.codec import encode
from clearmesh.crypto.keys import Ed25519Signer, verify
from clearmesh.crypto.merkle import merkle_root
from clearmesh.execution.executor import apply_block
from clearmesh.execution.mempool import Mempool
from clearmesh.state.overlay import Overlay
from clearmesh.state.roots import validators_hash
from clearmesh.state.store import Store
from clearmesh.types.block import Block, BlockHeader, Commit, CommitSig, block_hash, vote_sign_bytes
from clearmesh.types.tx import TxEnvelope


class SoloSequencer:
    def __init__(
        self,
        store: Store,
        signer: Ed25519Signer,
        chain_id: str,
        genesis_hash: bytes,
        validators_pubkeys: list[bytes],
        interval_s: float = 1.0,
        demo_evil_rpc: bool = False,
    ) -> None:
        self.store = store
        self.signer = signer
        self.chain_id = chain_id
        self.genesis_hash = genesis_hash
        self.validators_pubkeys = validators_pubkeys
        self.interval_s = interval_s
        self.demo_evil_rpc = demo_evil_rpc
        self.mempool = Mempool(chain_id=chain_id)
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._latest: tuple[Block, Commit] | None = None
        self._receipts: dict[int, list[Any]] = {}
        self._on_block: list[Callable[[Block, Commit, list[Any]], None]] = []
        # Base overlay reading from store
        self._height = store.last_height()

    def on_block(self, cb: Callable[[Block, Commit, list[Any]], None]) -> None:
        self._on_block.append(cb)

    @property
    def height(self) -> int:
        return self._height

    def submit_tx(self, env: TxEnvelope) -> tuple[bytes, bool, str]:
        base = Overlay(self.store)
        return self.mempool.add(env, base, self._height)

    def latest_block(self) -> tuple[Block, Commit] | None:
        return self._latest

    def get_receipts(self, height: int) -> list[Any]:
        return list(self._receipts.get(height, []))

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                self.produce_block()
            except Exception:  # noqa: BLE001
                # Keep sequencer alive; structlog would go here
                pass
            await asyncio.sleep(self.interval_s)

    def produce_block(self) -> tuple[Block, Commit]:
        height = self._height + 1
        base = Overlay(self.store)
        pol_raw = base.get("pol")
        max_tx = 100
        if pol_raw:
            from clearmesh.core.codec import decode
            from clearmesh.types.records import Policy

            max_tx = decode(Policy, pol_raw).max_tx_per_block

        txs = self.mempool.reap(max_tx, base, height, self.chain_id)
        prev = self.genesis_hash if height == 1 else (
            self._latest[0].header if self._latest else None
        )
        if height == 1:
            prev_hash = self.genesis_hash
            last_commit_hash = merkle_root([])
            parent_time = 0
        else:
            assert self._latest is not None
            prev_hash = block_hash(self._latest[0].header)
            last_commit_hash = merkle_root(
                [encode(s) for s in self._latest[1].sigs]
            )
            parent_time = self._latest[0].header.time_ms

        # Speculative header with placeholder roots
        overlay = Overlay(self.store)
        sanctions_v = 0
        from clearmesh.state.world import WorldView

        wv = WorldView(overlay)
        sanctions_v = wv.active_sanctions_version(height)

        provisional = BlockHeader(
            version=1,
            chain_id=self.chain_id,
            height=height,
            round=0,
            time_ms=max(parent_time + 1, int(time.time() * 1000)),
            prev_block_hash=prev_hash,
            last_commit_hash=last_commit_hash,
            tx_root=b"\x00" * 32,
            receipts_root=b"\x00" * 32,
            state_root=b"\x00" * 32,
            liabilities_root=b"\x00" * 32,
            validators_hash=validators_hash(self.validators_pubkeys),
            policy_hash=b"\x00" * 32,
            sanctions_version=sanctions_v,
            proposer_index=0,
        )
        block = Block(header=provisional, txs=tuple(txs), last_commit=None)
        result = apply_block(overlay, block, self.chain_id)
        header = BlockHeader(
            version=1,
            chain_id=self.chain_id,
            height=height,
            round=0,
            time_ms=provisional.time_ms,
            prev_block_hash=prev_hash,
            last_commit_hash=last_commit_hash,
            tx_root=result.roots["tx_root"],
            receipts_root=result.roots["receipts_root"],
            state_root=result.roots["state_root"],
            liabilities_root=result.roots["liabilities_root"],
            validators_hash=provisional.validators_hash,
            policy_hash=result.roots["policy_hash"],
            sanctions_version=sanctions_v,
            proposer_index=0,
        )
        block = Block(header=header, txs=tuple(txs), last_commit=None)
        bh = block_hash(header)
        # 1-of-1 commit using vote sign bytes style
        msg = vote_sign_bytes(self.chain_id, "PRECOMMIT", height, 0, bh)
        sig = self.signer.sign(msg)
        commit = Commit(
            height=height,
            round=0,
            block_hash=bh,
            sigs=(CommitSig(validator_index=0, sig=sig),),
        )
        self.store.commit_block(
            height=height,
            block_bytes=encode(block),
            commit_bytes=encode(commit),
            receipts_bytes=encode(result.receipts),
            roots=result.roots,
            writes=result.writes,
            tx_ids=result.tx_ids,
        )
        self._height = height
        self._latest = (block, commit)
        self._receipts[height] = result.receipts
        self.mempool.on_commit(result.tx_ids, height)
        for cb in self._on_block:
            cb(block, commit, result.receipts)
        return block, commit

    def verify_commit(self, commit: Commit, header: BlockHeader) -> bool:
        bh = block_hash(header)
        if commit.block_hash != bh:
            return False
        for cs in commit.sigs:
            if cs.validator_index >= len(self.validators_pubkeys):
                return False
            pub = self.validators_pubkeys[cs.validator_index]
            msg = vote_sign_bytes(self.chain_id, "PRECOMMIT", commit.height, commit.round, bh)
            if not verify(pub, msg, cs.sig):
                return False
        return True
