"""Per-debtor FIFO queue ordered by (priority, seq)."""

from __future__ import annotations

from clearmesh.state.world import WorldView


def _qkey(debtor: str, priority: int, seq: int) -> str:
    return f"q/{debtor}/{priority:01d}{seq:020d}"


def push(view: WorldView, debtor: str, priority: int, seq: int, uetr: str) -> None:
    view.o.put(_qkey(debtor, priority, seq), uetr.encode("utf-8"))


def remove(view: WorldView, debtor: str, priority: int, seq: int) -> None:
    view.o.delete(_qkey(debtor, priority, seq))


def head(view: WorldView, debtor: str) -> tuple[str, int, int] | None:
    """Return (uetr, priority, seq) of queue head or None."""
    prefix = f"q/{debtor}/"
    for k, v in view.o.scan(prefix):
        suffix = k.decode("utf-8")[len(prefix) :]
        priority = int(suffix[0])
        seq = int(suffix[1:])
        return v.decode("utf-8"), priority, seq
    return None


def items(view: WorldView, debtor: str) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    prefix = f"q/{debtor}/"
    for k, v in view.o.scan(prefix):
        suffix = k.decode("utf-8")[len(prefix) :]
        priority = int(suffix[0])
        seq = int(suffix[1:])
        out.append((v.decode("utf-8"), priority, seq))
    return out


def all_debtors(view: WorldView) -> list[str]:
    seen: list[str] = []
    have: set[str] = set()
    for k, _ in view.o.scan("q/"):
        parts = k.decode("utf-8").split("/")
        if len(parts) >= 2:
            d = parts[1]
            if d not in have:
                have.add(d)
                seen.append(d)
    return sorted(seen)
