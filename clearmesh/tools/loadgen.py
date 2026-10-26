"""Poisson traffic load generator with circular-flow share."""

from __future__ import annotations

import argparse
import random
import time
import uuid

import httpx


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rpc", default="http://127.0.0.1:26657")
    p.add_argument("--seconds", type=int, default=10)
    p.add_argument("--rate", type=float, default=5.0)
    args = p.parse_args()
    rng = random.Random(1)
    start = time.time()
    sent = 0
    while time.time() - start < args.seconds:
        # Placeholder: hits status to measure RPC; full tx path uses CLI keys
        httpx.get(f"{args.rpc}/v1/status", timeout=5)
        sent += 1
        delay = rng.expovariate(args.rate)
        time.sleep(min(delay, 1.0))
    elapsed = time.time() - start
    print(f"requests={sent} elapsed={elapsed:.2f}s tps={sent/elapsed:.2f}")


if __name__ == "__main__":
    main()
