"""python -m clearmesh.node --config node.toml"""

from __future__ import annotations

import argparse
import asyncio

from clearmesh.node.config import NodeConfig
from clearmesh.node.node import Node


async def _amain(config_path: str) -> None:
    cfg = NodeConfig.load(config_path)
    node = Node(cfg)
    await node.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        await node.stop()


def main() -> None:
    p = argparse.ArgumentParser(prog="clearmesh-node")
    p.add_argument("--config", required=True)
    args = p.parse_args()
    asyncio.run(_amain(args.config))


if __name__ == "__main__":
    main()
