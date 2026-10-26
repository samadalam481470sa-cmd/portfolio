"""SQLite WAL store with atomic per-block commits."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

from clearmesh.core.codec import encode


class StoreError(RuntimeError):
    pass


class Store:
    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> Store:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        store = cls(conn, path)
        store._init_schema()
        store._check_consistency()
        return store

    def _init_schema(self) -> None:
        c = self._conn
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
              k BLOB PRIMARY KEY,
              v BLOB NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS blocks (
              height INTEGER PRIMARY KEY,
              block BLOB NOT NULL,
              commit_blob BLOB NOT NULL,
              receipts BLOB NOT NULL,
              roots BLOB NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tx_index (
              tx_id BLOB PRIMARY KEY,
              height INTEGER NOT NULL,
              idx INTEGER NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
              k TEXT PRIMARY KEY,
              v BLOB NOT NULL
            )
            """
        )

    def _check_consistency(self) -> None:
        row = self._conn.execute(
            "SELECT v FROM meta WHERE k = ?", ("last_height",)
        ).fetchone()
        max_h = self._conn.execute("SELECT MAX(height) FROM blocks").fetchone()[0]
        if row is None:
            if max_h is not None:
                raise StoreError("blocks present without meta.last_height")
            return
        last = int.from_bytes(row[0], "big")
        if max_h is None:
            if last != 0:
                raise StoreError("meta.last_height without blocks")
            return
        if last != max_h:
            raise StoreError(f"meta.last_height={last} != max(blocks)={max_h}")

    def close(self) -> None:
        self._conn.close()

    def get(self, key: bytes | str) -> bytes | None:
        k = key.encode("utf-8") if isinstance(key, str) else key
        row = self._conn.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return None if row is None else row[0]

    def scan(self, prefix: bytes | str) -> Iterator[tuple[bytes, bytes]]:
        p = prefix.encode("utf-8") if isinstance(prefix, str) else prefix
        # lexicographic prefix scan
        end = p + b"\xff" * 64
        cur = self._conn.execute(
            "SELECT k, v FROM kv WHERE k >= ? AND k < ? ORDER BY k ASC",
            (p, end),
        )
        for k, v in cur:
            if not k.startswith(p):
                break
            yield k, v

    def last_height(self) -> int:
        row = self._conn.execute(
            "SELECT v FROM meta WHERE k = ?", ("last_height",)
        ).fetchone()
        if row is None:
            return 0
        return int.from_bytes(row[0], "big")

    def get_block(self, height: int) -> tuple[bytes, bytes, bytes, bytes] | None:
        row = self._conn.execute(
            "SELECT block, commit_blob, receipts, roots FROM blocks WHERE height = ?",
            (height,),
        ).fetchone()
        if row is None:
            return None
        return row[0], row[1], row[2], row[3]

    def get_tx_height(self, tx_id: bytes) -> tuple[int, int] | None:
        row = self._conn.execute(
            "SELECT height, idx FROM tx_index WHERE tx_id = ?", (tx_id,)
        ).fetchone()
        if row is None:
            return None
        return int(row[0]), int(row[1])

    def commit_block(
        self,
        height: int,
        block_bytes: bytes,
        commit_bytes: bytes,
        receipts_bytes: bytes,
        roots: dict[str, bytes],
        writes: list[tuple[bytes, bytes | None]],
        tx_ids: list[bytes],
    ) -> None:
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute(
                "INSERT INTO blocks(height, block, commit_blob, receipts, roots) VALUES (?,?,?,?,?)",
                (height, block_bytes, commit_bytes, receipts_bytes, encode(sorted(roots.items()))),
            )
            for i, tid in enumerate(tx_ids):
                c.execute(
                    "INSERT INTO tx_index(tx_id, height, idx) VALUES (?,?,?)",
                    (tid, height, i),
                )
            for k, v in writes:
                if v is None:
                    c.execute("DELETE FROM kv WHERE k = ?", (k,))
                else:
                    c.execute(
                        "INSERT INTO kv(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                        (k, v),
                    )
            c.execute(
                "INSERT INTO meta(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                ("last_height", height.to_bytes(8, "big")),
            )
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    def put_meta(self, key: str, value: bytes) -> None:
        self._conn.execute(
            "INSERT INTO meta(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            (key, value),
        )
