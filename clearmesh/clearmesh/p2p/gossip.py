"""Flood gossip with LRU dedupe."""

from __future__ import annotations

import hashlib
from collections import OrderedDict


class Gossip:
    def __init__(self, capacity: int = 10_000) -> None:
        self.capacity = capacity
        self._seen: OrderedDict[bytes, None] = OrderedDict()

    def seen(self, payload: bytes) -> bool:
        h = hashlib.sha256(payload).digest()
        if h in self._seen:
            self._seen.move_to_end(h)
            return True
        self._seen[h] = None
        if len(self._seen) > self.capacity:
            self._seen.popitem(last=False)
        return False
