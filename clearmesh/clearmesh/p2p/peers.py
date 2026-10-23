"""Static mesh, backoff, rate limits, misbehaviour score."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field


@dataclass
class PeerState:
    addr: str
    node_pubkey: bytes
    score: int = 0
    banned_until: float = 0.0
    tokens: float = 50.0
    last_refill: float = field(default_factory=time.time)
    backoff_s: float = 0.5


class PeerBook:
    def __init__(self, peers: list[tuple[str, bytes]], ban_threshold: int = 100) -> None:
        self.peers = {addr: PeerState(addr, pub) for addr, pub in peers}
        self.ban_threshold = ban_threshold

    def allowlisted(self, pubkey: bytes) -> bool:
        return any(p.node_pubkey == pubkey for p in self.peers.values())

    def note_bad(self, addr: str, points: int = 10) -> None:
        p = self.peers.get(addr)
        if not p:
            return
        p.score += points
        if p.score >= self.ban_threshold:
            p.banned_until = time.time() + 600

    def is_banned(self, addr: str) -> bool:
        p = self.peers.get(addr)
        return bool(p and time.time() < p.banned_until)

    def take_token(self, addr: str) -> bool:
        p = self.peers.get(addr)
        if not p:
            return False
        now = time.time()
        elapsed = now - p.last_refill
        p.tokens = min(50.0, p.tokens + elapsed * 10)
        p.last_refill = now
        if p.tokens < 1:
            return False
        p.tokens -= 1
        return True

    def next_backoff(self, addr: str) -> float:
        p = self.peers.get(addr)
        if not p:
            return 0.5
        delay = p.backoff_s + random.uniform(0, 0.1)
        p.backoff_s = min(30.0, p.backoff_s * 2)
        return delay

    def reset_backoff(self, addr: str) -> None:
        p = self.peers.get(addr)
        if p:
            p.backoff_s = 0.5
