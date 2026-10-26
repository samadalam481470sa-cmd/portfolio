"""Virtual clock for deterministic simulation."""

from __future__ import annotations


class VirtualClock:
    def __init__(self, start_ms: int = 0) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> None:
        if ms < 0:
            raise ValueError("cannot go backwards")
        self._now += ms
