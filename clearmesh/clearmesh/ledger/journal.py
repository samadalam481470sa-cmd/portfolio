"""Double-entry journal with contra issuance accounts."""

from __future__ import annotations

from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Posting
from clearmesh.types.records import AssetMeta


def post(view: WorldView, entries: list[Posting]) -> None:
    """Apply postings that sum to zero per asset; no non-contra negative balances."""
    by_asset: dict[str, int] = {}
    for e in entries:
        by_asset[e.asset] = by_asset.get(e.asset, 0) + e.delta
    for asset, s in by_asset.items():
        if s != 0:
            raise TxReject(ReasonCode.AG02, f"postings do not balance for {asset}")

    for e in entries:
        bal = view.get_balance(e.account, e.asset)
        new = bal + e.delta
        if new >= 2**63 or new < -(2**63 - 1):
            raise TxReject(ReasonCode.AG02, "balance overflow")
        if not e.account.startswith("sys:issuance:") and new < 0:
            raise TxReject(ReasonCode.AM04, f"insufficient funds {e.account}/{e.asset}")
        view.put_balance(e.account, e.asset, new)


def issue(view: WorldView, asset: str, to: str, amt: int) -> list[Posting]:
    if amt <= 0 or amt >= 2**63:
        raise TxReject(ReasonCode.FF01, "bad issue amount")
    contra = f"sys:issuance:{asset}"
    meta = view.get_asset(asset)
    if meta is None:
        raise TxReject(ReasonCode.FF01, f"unknown asset {asset}")
    new_supply = meta.total_supply + amt
    if new_supply >= 2**63:
        raise TxReject(ReasonCode.AG02, "supply overflow")
    entries = [
        Posting(account=contra, asset=asset, delta=-amt),
        Posting(account=to, asset=asset, delta=amt),
    ]
    post(view, entries)
    view.put_asset(
        asset,
        AssetMeta(decimals=meta.decimals, issuer_role=meta.issuer_role, total_supply=new_supply),
    )
    return entries


def redeem(view: WorldView, asset: str, frm: str, amt: int) -> list[Posting]:
    if amt <= 0 or amt >= 2**63:
        raise TxReject(ReasonCode.FF01, "bad redeem amount")
    contra = f"sys:issuance:{asset}"
    meta = view.get_asset(asset)
    if meta is None:
        raise TxReject(ReasonCode.FF01, f"unknown asset {asset}")
    if meta.total_supply < amt:
        raise TxReject(ReasonCode.AM04, "redeem exceeds supply")
    entries = [
        Posting(account=frm, asset=asset, delta=-amt),
        Posting(account=contra, asset=asset, delta=amt),
    ]
    post(view, entries)
    view.put_asset(
        asset,
        AssetMeta(
            decimals=meta.decimals,
            issuer_role=meta.issuer_role,
            total_supply=meta.total_supply - amt,
        ),
    )
    return entries


def check_invariants(view: WorldView) -> list[str]:
    """Return list of invariant violations (empty if healthy)."""
    errs: list[str] = []
    assets: set[str] = set()
    for k, _ in view.o.scan("asset/"):
        assets.add(k.decode().split("/", 1)[1])
    for asset in sorted(assets):
        meta = view.get_asset(asset)
        assert meta is not None
        total = 0
        contra = 0
        for k, v in view.o.scan(f"bal/"):
            parts = k.decode().split("/")
            if len(parts) != 3 or parts[2] != asset:
                continue
            from clearmesh.core.codec import decode

            bal = decode(int, v)  # type: ignore[arg-type]
            pid = parts[1]
            if pid.startswith("sys:issuance:"):
                contra += bal
            else:
                if bal < 0:
                    errs.append(f"negative balance {pid}/{asset}")
                total += bal
        if total != -contra:
            errs.append(f"sum(balances)={total} != -contra={-contra} for {asset}")
        if total != meta.total_supply:
            errs.append(f"sum(balances)={total} != supply={meta.total_supply} for {asset}")

    # Queue consistency
    queued_ueters: list[str] = []
    for k, v in view.o.scan("q/"):
        queued_ueters.append(v.decode() if isinstance(v, (bytes, bytearray)) else str(v))
    # values are uetr strings encoded as CBOR or raw?
    # We'll store raw utf-8 uetr bytes in queue
    for k, v in view.o.scan("q/"):
        uetr = v.decode("utf-8")
        instr = view.get_instruction(uetr)
        if instr is None or instr.status != "QUEUED":
            errs.append(f"queue entry {uetr} not QUEUED")
    for k, _ in view.o.scan("instr/"):
        uetr = k.decode().split("/", 1)[1]
        instr = view.get_instruction(uetr)
        if instr and instr.status == "QUEUED":
            # must appear exactly once in q/
            found = 0
            for qk, qv in view.o.scan(f"q/{instr.debtor}/"):
                if qv.decode("utf-8") == uetr:
                    found += 1
            if found != 1:
                errs.append(f"QUEUED {uetr} appears {found} times in queue")
    return errs
