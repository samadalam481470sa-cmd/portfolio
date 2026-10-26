"""ConsensusEngine protocol."""

from __future__ import annotations

from typing import Protocol

from clearmesh.types.block import Block, Commit
from clearmesh.types.tx import TxEnvelope


class ConsensusEngine(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def submit_tx(self, env: TxEnvelope) -> tuple[bytes, bool, str]: ...

    @property
    def height(self) -> int: ...

    def latest_block(self) -> tuple[Block, Commit] | None: ...
