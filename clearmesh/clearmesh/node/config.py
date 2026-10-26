"""TOML node configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NodeConfig:
    chain_id: str = "clearmesh-sim-1"
    data_dir: str = "./data"
    genesis_path: str = "./genesis.json"
    listen_host: str = "127.0.0.1"
    listen_port: int = 26656
    rpc_host: str = "127.0.0.1"
    rpc_port: int = 26657
    validator_key_path: str = "./keys/node.key"
    peers: list[dict] = field(default_factory=list)
    demo_evil_rpc: bool = False
    solo: bool = True
    block_interval_s: float = 1.0

    @staticmethod
    def load(path: str | Path) -> NodeConfig:
        text = Path(path).read_text(encoding="utf-8")
        data = tomllib.loads(text)
        return NodeConfig(
            chain_id=data.get("chain_id", "clearmesh-sim-1"),
            data_dir=data.get("data_dir", "./data"),
            genesis_path=data.get("genesis_path", "./genesis.json"),
            listen_host=data.get("listen_host", "127.0.0.1"),
            listen_port=int(data.get("listen_port", 26656)),
            rpc_host=data.get("rpc_host", "127.0.0.1"),
            rpc_port=int(data.get("rpc_port", 26657)),
            validator_key_path=data.get("validator_key_path", "./keys/node.key"),
            peers=list(data.get("peers", [])),
            demo_evil_rpc=bool(data.get("demo_evil_rpc", False)),
            solo=bool(data.get("solo", True)),
            block_interval_s=float(data.get("block_interval_s", 1.0)),
        )
