"""Seeded delay/drop/dup/reorder/partition transport model."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class NetConfig:
    delay_ms: int = 10
    delay_jitter_ms: int = 5
    drop_rate: float = 0.0
    dup_rate: float = 0.0
    reorder_window: int = 0
    partitions: list[set[int]] = field(default_factory=list)


class SimNetwork:
    def __init__(self, n: int, seed: int, cfg: NetConfig | None = None) -> None:
        self.n = n
        self.rng = random.Random(seed)
        self.cfg = cfg or NetConfig()
        self._queues: list[list[tuple[int, int, bytes]]] = [[] for _ in range(n)]
        # (deliver_at_ms, from, payload)

    def partitioned(self, a: int, b: int) -> bool:
        for part in self.cfg.partitions:
            if (a in part) != (b in part) and (a in part or b in part):
                # if they are in different partition sets when partitions defined
                pass
        if not self.cfg.partitions:
            return False
        # nodes can only talk within same partition set
        for part in self.cfg.partitions:
            if a in part and b in part:
                return False
        return True

    def send(self, now_ms: int, src: int, dst: int, payload: bytes) -> None:
        if src == dst or self.partitioned(src, dst):
            return
        if self.rng.random() < self.cfg.drop_rate:
            return
        delay = self.cfg.delay_ms + self.rng.randint(0, self.cfg.delay_jitter_ms)
        if self.cfg.reorder_window:
            delay += self.rng.randint(0, self.cfg.reorder_window)
        self._queues[dst].append((now_ms + delay, src, payload))
        if self.rng.random() < self.cfg.dup_rate:
            self._queues[dst].append((now_ms + delay + 1, src, payload))

    def recv_due(self, node: int, now_ms: int) -> list[tuple[int, bytes]]:
        due = [x for x in self._queues[node] if x[0] <= now_ms]
        self._queues[node] = [x for x in self._queues[node] if x[0] > now_ms]
        due.sort(key=lambda x: x[0])
        return [(src, payload) for _, src, payload in due]
