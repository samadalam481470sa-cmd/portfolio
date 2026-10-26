"""Last-signed (h, r, step) persisted BEFORE any signature leaves the process."""

from __future__ import annotations

import json
import os
from pathlib import Path

from clearmesh.crypto.keys import Ed25519Signer


class DoubleSignError(RuntimeError):
    pass


class PrivValidator:
    def __init__(self, path: str | Path, signer: Ed25519Signer) -> None:
        self.path = Path(path)
        self.signer = signer
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"h": 0, "r": -1, "step": "", "hash": None, "sig": None}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _persist(self, state: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        data = json.dumps(state, sort_keys=True).encode("utf-8")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        # fsync directory for durability
        dir_fd = os.open(str(self.path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def sign_vote(
        self, height: int, round_: int, step: str, block_hash: bytes | None, msg: bytes
    ) -> bytes:
        st = self._state
        prev = (st["h"], st["r"], st["step"])
        cur = (height, round_, step)
        hex_hash = None if block_hash is None else block_hash.hex()

        if cur < prev:
            raise DoubleSignError("refusing lower (h,r,step)")
        if cur == prev:
            if st.get("hash") == hex_hash and st.get("sig"):
                return bytes.fromhex(st["sig"])
            raise DoubleSignError("same (h,r,step) different hash")

        # Write-before-sign
        new_state = {
            "h": height,
            "r": round_,
            "step": step,
            "hash": hex_hash,
            "sig": None,
        }
        self._persist(new_state)
        sig = self.signer.sign(msg)
        new_state["sig"] = sig.hex()
        self._persist(new_state)
        self._state = new_state
        return sig
