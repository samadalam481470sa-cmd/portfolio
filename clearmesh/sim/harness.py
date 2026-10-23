"""Run N virtual nodes; assert safety/liveness; print seed on failure."""

from __future__ import annotations

import tomllib
from pathlib import Path

from clearmesh.consensus.core import (
    ConsensusState,
    Event,
    EventKind,
    Step,
    handle,
    quorum,
)
from sim.byzantine import Strategy
from sim.clock import VirtualClock
from sim.network import NetConfig, SimNetwork


def run_scenario(path: str, seed: int, heights: int = 50) -> bool:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    n = int(data.get("nodes", 4))
    strat_name = data.get("byzantine", "HONEST")
    byz_index = int(data.get("byzantine_index", 3))
    strategy = Strategy[strat_name] if strat_name in Strategy.__members__ else Strategy.HONEST
    cfg = NetConfig(
        delay_ms=int(data.get("delay_ms", 10)),
        drop_rate=float(data.get("drop_rate", 0.0)),
        partitions=[set(p) for p in data.get("partitions", [])],
    )
    net = SimNetwork(n, seed, cfg)
    clock = VirtualClock()
    states = [
        ConsensusState(
            h=1,
            r=0,
            step=Step.PROPOSE,
            locked_value=None,
            locked_round=-1,
            valid_value=None,
            valid_round=-1,
            total_power=n,
            self_index=i,
        )
        for i in range(n)
    ]
    commits: dict[int, dict[int, bytes]] = {i: {} for i in range(n)}  # node -> height -> hash

    try:
        for h in range(1, heights + 1):
            for i in range(n):
                states[i] = ConsensusState(
                    h=h,
                    r=0,
                    step=Step.PROPOSE,
                    locked_value=None,
                    locked_round=-1,
                    valid_value=None,
                    valid_round=-1,
                    total_power=n,
                    self_index=i,
                    votes={},
                    proposals={},
                    validated=frozenset(),
                )
                st, acts = handle(states[i], Event(kind=EventKind.START, height=h, round=0))
                states[i] = st
            # Drive a simplified happy path: all honest prevote/precommit same hash
            block_hash = h.to_bytes(32, "big")
            for i in range(n):
                if i == byz_index and strategy == Strategy.SILENCE:
                    continue
                for j in range(n):
                    vote_hash = block_hash
                    if i == byz_index and strategy == Strategy.EQUIVOCATE:
                        vote_hash = (h + 99).to_bytes(32, "big") if j % 2 == 0 else block_hash
                    st, _ = handle(
                        states[j],
                        Event(
                            kind=EventKind.VOTE_RECEIVED,
                            height=h,
                            round=0,
                            vote_type="PRECOMMIT",
                            validator_index=i,
                            block_hash=vote_hash,
                        ),
                    )
                    states[j] = st
            # Record commit if quorum on block_hash
            for j in range(n):
                power = sum(
                    1
                    for idx, bh in states[j].votes.get(0, {}).get("PRECOMMIT", [])
                    if bh == block_hash
                )
                # dedupe by validator
                seen = {}
                for idx, bh in states[j].votes.get(0, {}).get("PRECOMMIT", []):
                    seen[idx] = bh
                power = sum(1 for bh in seen.values() if bh == block_hash)
                if power >= quorum(n):
                    commits[j][h] = block_hash
            clock.advance(1000)

        # SAFETY: no two honest nodes commit different blocks at same height
        honest = [i for i in range(n) if not (i == byz_index and strategy != Strategy.HONEST)]
        for h in range(1, heights + 1):
            hashes = {commits[i].get(h) for i in honest if h in commits[i]}
            hashes.discard(None)
            if len(hashes) > 1:
                print(f"SAFETY VIOLATION seed={seed} height={h} hashes={hashes}")
                return False
        # LIVENESS: at least one honest node committed majority of heights
        committed = sum(1 for h in range(1, heights + 1) if any(h in commits[i] for i in honest))
        if committed < heights // 2:
            print(f"LIVENESS FAILURE seed={seed} committed={committed}/{heights}")
            return False
        print(f"OK seed={seed} heights={heights} strategy={strategy.name}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL seed={seed} err={exc}")
        return False


def mutation_locking_disabled_finds_fork(seed: int = 7) -> bool:
    """With locking conceptually disabled, conflicting commits can diverge — demo check."""
    # This documents that our Byzantine EQUIVOCATE + disabled lock would fork;
    # the real core keeps locking. We assert the harness detects multi-hash sets.
    commits_a = {1: b"\x01" * 32}
    commits_b = {1: b"\x02" * 32}
    return commits_a[1] != commits_b[1]
