"""Asyncio glue: timers, executor, WAL, privval, network actions."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from clearmesh.consensus.core import (
    Action,
    ActionKind,
    ConsensusState,
    Event,
    EventKind,
    Step,
    handle,
)
from clearmesh.consensus.privval import PrivValidator
from clearmesh.consensus.wal import WAL
from clearmesh.core.codec import encode
from clearmesh.types.block import vote_sign_bytes


class ConsensusDriver:
    def __init__(
        self,
        wal: WAL,
        privval: PrivValidator,
        chain_id: str,
        self_index: int,
        total_power: int = 4,
        broadcast: Callable[[bytes], Any] | None = None,
    ) -> None:
        self.wal = wal
        self.privval = privval
        self.chain_id = chain_id
        self.broadcast = broadcast or (lambda _b: None)
        self.cs = ConsensusState(
            h=1,
            r=0,
            step=Step.PROPOSE,
            locked_value=None,
            locked_round=-1,
            valid_value=None,
            valid_round=-1,
            total_power=total_power,
            self_index=self_index,
        )
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._timers: dict[tuple[int, int, str], asyncio.Task[None]] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self, height: int) -> None:
        self.cs = ConsensusState(
            h=height,
            r=0,
            step=Step.PROPOSE,
            locked_value=None,
            locked_round=-1,
            valid_value=None,
            valid_round=-1,
            total_power=self.cs.total_power,
            self_index=self.cs.self_index,
        )
        await self._queue.put(Event(kind=EventKind.START, height=height, round=0))
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for t in self._timers.values():
            t.cancel()

    async def push(self, ev: Event) -> None:
        await self._queue.put(ev)

    async def _run(self) -> None:
        while True:
            ev = await self._queue.get()
            self.wal.append(encode([ev.kind.value, ev.height, ev.round, ev.step]))
            self.cs, actions = handle(self.cs, ev)
            for act in actions:
                await self._do(act)

    async def _do(self, act: Action) -> None:
        if act.kind == ActionKind.SCHEDULE_TIMEOUT:
            p = act.payload
            key = (p["h"], p["r"], p["step"])

            async def _fire() -> None:
                await asyncio.sleep(p["ms"] / 1000.0)
                await self.push(
                    Event(
                        kind=EventKind.TIMEOUT,
                        height=p["h"],
                        round=p["r"],
                        step=p["step"],
                    )
                )

            old = self._timers.pop(key, None)
            if old:
                old.cancel()
            self._timers[key] = asyncio.create_task(_fire())
        elif act.kind == ActionKind.SIGN_AND_BROADCAST:
            p = act.payload
            if p["type"] in ("PREVOTE", "PRECOMMIT"):
                msg = vote_sign_bytes(
                    self.chain_id, p["type"], p["h"], p["r"], p.get("hash")
                )
                sig = self.privval.sign_vote(p["h"], p["r"], p["type"], p.get("hash"), msg)
                self.broadcast(encode([p["type"], p["h"], p["r"], p.get("hash"), sig]))
        elif act.kind == ActionKind.BROADCAST:
            self.broadcast(act.payload if isinstance(act.payload, bytes) else encode(act.payload))
