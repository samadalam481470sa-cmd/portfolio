"""Mempool with idempotent submission and cheap checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from clearmesh.core.codec import encode
from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.execution.executor import check_stateless
from clearmesh.execution.handlers import handle_tx
from clearmesh.state.overlay import Overlay
from clearmesh.state.world import WorldView
from clearmesh.types.tx import TxEnvelope, TxType, tx_id


@dataclass
class Mempool:
    chain_id: str
    max_size: int = 10_000
    _items: dict[bytes, TxEnvelope] = field(default_factory=dict)
    _order: list[bytes] = field(default_factory=list)
    _verified: set[bytes] = field(default_factory=set)

    def add(self, env: TxEnvelope, committed: Overlay, height: int) -> tuple[bytes, bool, str]:
        raw = encode(env)
        if len(raw) > 64 * 1024:
            return b"", False, ReasonCode.FF01.value
        if env.chain_id != self.chain_id:
            return b"", False, ReasonCode.FF01.value
        world = WorldView(committed)
        pol = world.get_policy()
        max_ttl = pol.max_tx_ttl if pol else 100
        try:
            check_stateless(env, self.chain_id, height, max_ttl)
        except TxReject as e:
            return b"", False, e.code.value

        tid = tx_id(env)
        if tid in self._items:
            return tid, True, ReasonCode.OK.value
        if world.o.get(f"seen/{env.valid_until_height:020d}/{tid.hex()}") is not None:
            return tid, True, ReasonCode.OK.value

        # Role / payment checks against committed state
        try:
            if TxType(env.tx_type) == TxType.PAYMENT_INSTRUCTION:
                from clearmesh.compliance.policy import check_payment

                check_payment(world, env, height)
        except TxReject as e:
            return tid, False, e.code.value

        if len(self._items) >= self.max_size:
            return tid, False, ReasonCode.MS03.value

        self._items[tid] = env
        self._order.append(tid)
        self._verified.add(tid)
        return tid, True, ReasonCode.OK.value

    def reap(self, max_txs: int, base: Overlay, height: int, chain_id: str) -> list[TxEnvelope]:
        selected: list[TxEnvelope] = []
        overlay = Overlay(base)
        for tid in list(self._order):
            if len(selected) >= max_txs:
                break
            env = self._items.get(tid)
            if env is None:
                continue
            child = overlay.child()
            try:
                handle_tx(WorldView(child), env, height)
                child.apply_to_parent()
                selected.append(env)
            except TxReject:
                continue
        return selected

    def on_commit(self, included: list[bytes], height: int) -> None:
        drop = set(included)
        for tid in list(self._order):
            env = self._items.get(tid)
            if env is None or tid in drop or env.valid_until_height <= height:
                self._items.pop(tid, None)
                self._verified.discard(tid)
        self._order = [t for t in self._order if t in self._items]

    def size(self) -> int:
        return len(self._items)
