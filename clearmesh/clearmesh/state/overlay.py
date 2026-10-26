"""Copy-on-write overlay for speculative execution."""

from __future__ import annotations

from typing import Iterator, Protocol


class KVView(Protocol):
    def get(self, key: bytes | str) -> bytes | None: ...

    def scan(self, prefix: bytes | str) -> Iterator[tuple[bytes, bytes]]: ...


class Overlay:
    def __init__(self, base: KVView) -> None:
        self._base = base
        self._puts: dict[bytes, bytes] = {}
        self._deletes: set[bytes] = set()

    def _key(self, key: bytes | str) -> bytes:
        return key.encode("utf-8") if isinstance(key, str) else key

    def get(self, key: bytes | str) -> bytes | None:
        k = self._key(key)
        if k in self._deletes:
            return None
        if k in self._puts:
            return self._puts[k]
        return self._base.get(k)

    def put(self, key: bytes | str, value: bytes) -> None:
        k = self._key(key)
        self._deletes.discard(k)
        self._puts[k] = value

    def delete(self, key: bytes | str) -> None:
        k = self._key(key)
        self._puts.pop(k, None)
        self._deletes.add(k)

    def scan(self, prefix: bytes | str) -> Iterator[tuple[bytes, bytes]]:
        p = self._key(prefix)
        # Merge base scan with overlay
        base_items = list(self._base.scan(p))
        merged: dict[bytes, bytes | None] = {k: v for k, v in base_items}
        for k, v in self._puts.items():
            if k.startswith(p):
                merged[k] = v
        for k in self._deletes:
            if k.startswith(p):
                merged[k] = None
        for k in sorted(merged.keys()):
            v = merged[k]
            if v is not None:
                yield k, v

    def child(self) -> Overlay:
        """Per-transaction rollback overlay."""
        return Overlay(self)

    def diff(self) -> list[tuple[bytes, bytes | None]]:
        out: list[tuple[bytes, bytes | None]] = []
        for k in sorted(set(self._puts) | self._deletes):
            if k in self._deletes:
                out.append((k, None))
            else:
                out.append((k, self._puts[k]))
        return out

    def apply_to_parent(self) -> None:
        if not isinstance(self._base, Overlay):
            raise TypeError("apply_to_parent requires Overlay base")
        parent: Overlay = self._base
        for k, v in self.diff():
            if v is None:
                parent.delete(k)
            else:
                parent.put(k, v)
