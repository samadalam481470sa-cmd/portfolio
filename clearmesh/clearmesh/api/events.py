"""In-process pub/sub for WebSocket events."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def subscribe(self, participant: str | None = None) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        key = participant or "*"
        self._subs[key].append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]], participant: str | None = None) -> None:
        key = participant or "*"
        if q in self._subs[key]:
            self._subs[key].remove(q)

    def publish(self, event: dict[str, Any], participant: str | None = None) -> None:
        targets = list(self._subs.get("*", []))
        if participant:
            targets.extend(self._subs.get(participant, []))
        for q in targets:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
