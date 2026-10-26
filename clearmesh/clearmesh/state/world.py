"""Typed get/put over the Clearmesh keyspace."""

from __future__ import annotations

from typing import TypeVar

from clearmesh.core.codec import decode, encode
from clearmesh.state.overlay import Overlay
from clearmesh.types.records import (
    Account,
    AssetMeta,
    Group,
    Instruction,
    NettingReport,
    Participant,
    Policy,
    SanctionsListMeta,
)

T = TypeVar("T")


class WorldView:
    def __init__(self, overlay: Overlay) -> None:
        self.o = overlay

    def _get(self, cls: type[T], key: str) -> T | None:
        raw = self.o.get(key)
        if raw is None:
            return None
        return decode(cls, raw)

    def _put(self, key: str, obj: object) -> None:
        self.o.put(key, encode(obj))

    def get_participant(self, pid: str) -> Participant | None:
        return self._get(Participant, f"part/{pid}")

    def put_participant(self, p: Participant) -> None:
        self._put(f"part/{p.id}", p)

    def get_account(self, pid: str) -> Account | None:
        return self._get(Account, f"acct/{pid}")

    def put_account(self, pid: str, acct: Account) -> None:
        self._put(f"acct/{pid}", acct)

    def get_balance(self, pid: str, asset: str) -> int:
        raw = self.o.get(f"bal/{pid}/{asset}")
        if raw is None:
            return 0
        return decode(int, raw)  # type: ignore[arg-type, return-value]

    def put_balance(self, pid: str, asset: str, value: int) -> None:
        self.o.put(f"bal/{pid}/{asset}", encode(value))

    def get_asset(self, asset: str) -> AssetMeta | None:
        return self._get(AssetMeta, f"asset/{asset}")

    def put_asset(self, asset: str, meta: AssetMeta) -> None:
        self._put(f"asset/{asset}", meta)

    def get_instruction(self, uetr: str) -> Instruction | None:
        return self._get(Instruction, f"instr/{uetr}")

    def put_instruction(self, instr: Instruction) -> None:
        self._put(f"instr/{instr.uetr}", instr)

    def get_group(self, group_id: bytes) -> Group | None:
        return self._get(Group, f"grp/{group_id.hex()}")

    def put_group(self, g: Group) -> None:
        self._put(f"grp/{g.group_id.hex()}", g)

    def get_policy(self) -> Policy | None:
        return self._get(Policy, "pol")

    def put_policy(self, pol: Policy) -> None:
        self._put("pol", pol)

    def get_sanctions(self, version: int) -> SanctionsListMeta | None:
        return self._get(SanctionsListMeta, f"sanc/{version}")

    def put_sanctions(self, meta: SanctionsListMeta) -> None:
        self._put(f"sanc/{meta.version}", meta)

    def get_netting(self, cycle: bytes) -> NettingReport | None:
        return self._get(NettingReport, f"nrep/{cycle.hex()}")

    def put_netting(self, rep: NettingReport) -> None:
        self._put(f"nrep/{rep.cycle_id.hex()}", rep)

    def next_seq(self) -> int:
        raw = self.o.get("meta/seq")
        cur = 0 if raw is None else int.from_bytes(raw, "big")
        nxt = cur + 1
        self.o.put("meta/seq", nxt.to_bytes(8, "big"))
        return nxt

    def mark_uetr(self, uetr: str) -> None:
        self.o.put(f"uetr/{uetr}", b"")

    def uetr_seen(self, uetr: str) -> bool:
        return self.o.get(f"uetr/{uetr}") is not None

    def mark_seen(self, valid_until: int, tx_id: bytes) -> None:
        self.o.put(f"seen/{valid_until:020d}/{tx_id.hex()}", b"")

    def seen(self, valid_until: int, tx_id: bytes) -> bool:
        # also scan any window — callers typically know valid_until
        return self.o.get(f"seen/{valid_until:020d}/{tx_id.hex()}") is not None

    def active_sanctions_version(self, height: int) -> int:
        best = 0
        for k, _ in self.o.scan("sanc/"):
            ver = int(k.decode().split("/", 1)[1])
            meta = self.get_sanctions(ver)
            if meta and meta.effective_height <= height and ver > best:
                best = ver
        return best
