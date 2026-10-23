"""Node wiring: store, genesis, consensus, RPC."""

from __future__ import annotations

import asyncio
from pathlib import Path

from clearmesh.consensus.solo import SoloSequencer
from clearmesh.crypto.keys import Ed25519Signer
from clearmesh.crypto.keystore import load_keystore
from clearmesh.node.config import NodeConfig
from clearmesh.node.genesis import Genesis, genesis_hash, init_genesis_state
from clearmesh.state.store import Store


class Node:
    def __init__(self, config: NodeConfig, password: str = "testnet") -> None:
        self.config = config
        self.password = password
        self.store: Store | None = None
        self.sequencer: SoloSequencer | None = None
        self.genesis: Genesis | None = None
        self._rpc_task: asyncio.Task[None] | None = None
        self._server = None

    async def start(self) -> None:
        cfg = self.config
        Path(cfg.data_dir).mkdir(parents=True, exist_ok=True)
        self.genesis = Genesis.load(cfg.genesis_path)
        ghash = genesis_hash(self.genesis)
        db_path = Path(cfg.data_dir) / "clearmesh.sqlite"
        self.store = Store.open(db_path)
        init_genesis_state(self.store, self.genesis)

        seed = load_keystore(cfg.validator_key_path, self.password)
        signer = Ed25519Signer(seed)
        pubs = [bytes.fromhex(v.pubkey_hex) for v in self.genesis.validators]
        self.sequencer = SoloSequencer(
            store=self.store,
            signer=signer,
            chain_id=cfg.chain_id,
            genesis_hash=ghash,
            validators_pubkeys=pubs,
            interval_s=cfg.block_interval_s,
            demo_evil_rpc=cfg.demo_evil_rpc,
        )
        await self.sequencer.start()

        from clearmesh.api.rpc import create_app
        import uvicorn

        app = create_app(self)
        config = uvicorn.Config(
            app, host=cfg.rpc_host, port=cfg.rpc_port, log_level="info"
        )
        self._server = uvicorn.Server(config)
        self._rpc_task = asyncio.create_task(self._server.serve())

    async def stop(self) -> None:
        if self.sequencer:
            await self.sequencer.stop()
        if self._server:
            self._server.should_exit = True
        if self._rpc_task:
            try:
                await self._rpc_task
            except Exception:  # noqa: BLE001
                pass
        if self.store:
            self.store.close()
