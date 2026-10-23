"""~naive dict ledger for differential testing against the real engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RefLedger:
    balances: dict[tuple[str, str], int] = field(default_factory=dict)
    supply: dict[str, int] = field(default_factory=dict)
    seen_uetr: set[str] = field(default_factory=set)
    status: dict[str, str] = field(default_factory=dict)

    def issue(self, asset: str, to: str, amt: int) -> None:
        self.balances[(to, asset)] = self.balances.get((to, asset), 0) + amt
        self.supply[asset] = self.supply.get(asset, 0) + amt

    def pay_interbank(self, uetr: str, debtor: str, creditor: str, asset: str, amt: int) -> None:
        if uetr in self.seen_uetr:
            raise ValueError("dup")
        if self.balances.get((debtor, asset), 0) < amt:
            self.status[uetr] = "QUEUED"
            return
        self.balances[(debtor, asset)] -= amt
        self.balances[(creditor, asset)] = self.balances.get((creditor, asset), 0) + amt
        self.seen_uetr.add(uetr)
        self.status[uetr] = "SETTLED"

    def balance(self, pid: str, asset: str) -> int:
        return self.balances.get((pid, asset), 0)
