"""fsync'd append-only consensus write-ahead log."""

from __future__ import annotations

import os
import struct
from pathlib import Path


class WAL:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "ab+", buffering=0)

    def append(self, record: bytes) -> None:
        header = struct.pack(">I", len(record))
        self._fh.write(header + record)
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def replay(self) -> list[bytes]:
        self._fh.seek(0)
        out: list[bytes] = []
        while True:
            hdr = self._fh.read(4)
            if not hdr:
                break
            if len(hdr) < 4:
                break
            (n,) = struct.unpack(">I", hdr)
            data = self._fh.read(n)
            if len(data) < n:
                break
            out.append(data)
        return out

    def close(self) -> None:
        self._fh.close()
