"""Per (round, type) power tally with equivocation detection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AddResult:
    status: str  # new | dup | conflict
    evidence: tuple | None = None


@dataclass
class HeightVoteSet:
    total: int
    # (round, type) -> validator_index -> block_hash|None
    votes: dict[tuple[int, str], dict[int, bytes | None]] = field(default_factory=dict)

    @property
    def quorum(self) -> int:
        return self.total * 2 // 3 + 1

    def add(
        self, round_: int, vtype: str, validator_index: int, block_hash: bytes | None
    ) -> AddResult:
        key = (round_, vtype)
        bucket = self.votes.setdefault(key, {})
        if validator_index in bucket:
            if bucket[validator_index] == block_hash:
                return AddResult("dup")
            return AddResult(
                "conflict",
                evidence=(validator_index, round_, vtype, bucket[validator_index], block_hash),
            )
        bucket[validator_index] = block_hash
        return AddResult("new")

    def power_for(self, round_: int, vtype: str, block_hash: bytes | None) -> int:
        bucket = self.votes.get((round_, vtype), {})
        return sum(1 for h in bucket.values() if h == block_hash)

    def any_power(self, round_: int, vtype: str) -> int:
        return len(self.votes.get((round_, vtype), {}))

    def has_quorum(self, round_: int, vtype: str, block_hash: bytes | None) -> bool:
        return self.power_for(round_, vtype, block_hash) >= self.quorum
