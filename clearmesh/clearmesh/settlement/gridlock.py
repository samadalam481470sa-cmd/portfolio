"""Deterministic multilateral netting (Bech–Soramäki style heuristic)."""

from __future__ import annotations

from dataclasses import replace

from clearmesh.crypto.hashing import h
from clearmesh.ledger.journal import post
from clearmesh.settlement import queue as Q
from clearmesh.settlement.lifecycle import transition
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Posting, Receipt
from clearmesh.types.records import AssetStat, NettingReport


def run(view: WorldView, height: int) -> tuple[list[Receipt], NettingReport]:
    """Pure integer netting cycle. Returns receipts and report."""
    # Build units: queued singletons + armed groups
    units: list[dict] = []
    for debtor in Q.all_debtors(view):
        acct = view.get_account(debtor)
        if acct and acct.frozen:
            continue
        for uetr, prio, seq in Q.items(view, debtor):
            instr = view.get_instruction(uetr)
            if instr is None or instr.status != "QUEUED":
                continue
            c_acct = view.get_account(instr.creditor)
            if c_acct and c_acct.frozen:
                continue
            units.append(
                {
                    "kind": "single",
                    "id": uetr.encode("utf-8"),
                    "uetr": uetr,
                    "priority": prio,
                    "admitted_height": instr.admitted_height,
                    "seq": seq,
                    "debtor": debtor,
                    "legs": [(instr.debtor, instr.creditor, instr.asset, instr.amount)],
                }
            )

    for k, _ in view.o.scan("gq/"):
        gid_hex = view.o.get(k)
        if gid_hex is None:
            continue
        gid = bytes.fromhex(gid_hex.decode("utf-8"))
        g = view.get_group(gid)
        if g is None or g.status != "ARMED":
            continue
        frozen = False
        for leg in g.legs:
            a = view.get_account(leg.payer)
            b = view.get_account(leg.payee)
            if (a and a.frozen) or (b and b.frozen):
                frozen = True
                break
        if frozen:
            continue
        units.append(
            {
                "kind": "group",
                "id": g.group_id,
                "priority": g.priority,
                "admitted_height": g.admitted_height,
                "seq": g.seq,
                "legs": [(leg.payer, leg.payee, leg.asset, leg.amount) for leg in g.legs],
                "payers": sorted({leg.payer for leg in g.legs}),
            }
        )

    units.sort(key=lambda u: (u["priority"], u["admitted_height"], u["seq"]))
    # active as list + index map (never iterate a Python set)
    active_ids = [u["id"] for u in units]
    by_id = {u["id"]: u for u in units}
    active_index = {uid: i for i, uid in enumerate(active_ids)}

    def sort_key(uid: bytes) -> tuple:
        u = by_id[uid]
        # LIFO among lowest priority → higher priority number first, then higher seq
        return (-u["priority"], -u["admitted_height"], -u["seq"])

    while True:
        # net[(p,a)] = balance + incoming - outgoing over active
        incoming: dict[tuple[str, str], int] = {}
        outgoing: dict[tuple[str, str], int] = {}
        for uid in active_ids:
            if uid not in active_index:
                continue
            u = by_id[uid]
            for payer, payee, asset, amt in u["legs"]:
                outgoing[(payer, asset)] = outgoing.get((payer, asset), 0) + amt
                incoming[(payee, asset)] = incoming.get((payee, asset), 0) + amt

        parties_assets: list[tuple[str, str]] = []
        seen_pa: set[tuple[str, str]] = set()
        for k in list(outgoing.keys()) + list(incoming.keys()):
            if k not in seen_pa:
                seen_pa.add(k)
                parties_assets.append(k)
        parties_assets.sort()

        violators: list[tuple[str, str]] = []
        for p, a in parties_assets:
            bal = view.get_balance(p, a)
            net = bal + incoming.get((p, a), 0) - outgoing.get((p, a), 0)
            cap = None
            acct = view.get_account(p)
            if acct:
                for asset, c in acct.debit_caps:
                    if asset == a:
                        cap = c
                        break
            out_in = outgoing.get((p, a), 0) - incoming.get((p, a), 0)
            if net < 0 or (cap is not None and out_in > cap):
                violators.append((p, a))
        if not violators:
            break

        removed_any = False
        for p, a in violators:
            cand: list[bytes] = []
            # last active singleton of p that debits p in asset a
            singles = [
                uid
                for uid in active_ids
                if uid in active_index
                and by_id[uid]["kind"] == "single"
                and by_id[uid]["debtor"] == p
                and any(leg[0] == p and leg[2] == a for leg in by_id[uid]["legs"])
            ]
            if singles:
                cand.append(singles[-1])
            for uid in active_ids:
                if uid not in active_index:
                    continue
                u = by_id[uid]
                if u["kind"] != "group":
                    continue
                # net outflow for p in a within group
                out_g = sum(amt for payer, _, asset, amt in u["legs"] if payer == p and asset == a)
                in_g = sum(amt for _, payee, asset, amt in u["legs"] if payee == p and asset == a)
                if out_g - in_g > 0:
                    cand.append(uid)
            if not cand:
                continue
            remove_id = max(cand, key=sort_key)
            _deactivate(active_ids, active_index, remove_id)
            removed_any = True
            u = by_id[remove_id]
            if u["kind"] == "group":
                # remove every later singleton of each of its payers
                for payer in u["payers"]:
                    later = [
                        uid
                        for uid in list(active_ids)
                        if uid in active_index
                        and by_id[uid]["kind"] == "single"
                        and by_id[uid]["debtor"] == payer
                        and (
                            by_id[uid]["priority"],
                            by_id[uid]["admitted_height"],
                            by_id[uid]["seq"],
                        )
                        > (u["priority"], u["admitted_height"], u["seq"])
                    ]
                    for uid in later:
                        _deactivate(active_ids, active_index, uid)
        if not removed_any:
            break

    # Apply net deltas in ONE journal post
    net_delta: dict[tuple[str, str], int] = {}
    settled_ids: list[bytes] = []
    deferred_ids: list[bytes] = []
    for uid, u in by_id.items():
        if uid in active_index:
            settled_ids.append(uid)
            for payer, payee, asset, amt in u["legs"]:
                net_delta[(payer, asset)] = net_delta.get((payer, asset), 0) - amt
                net_delta[(payee, asset)] = net_delta.get((payee, asset), 0) + amt
        else:
            deferred_ids.append(uid)

    settled_ids.sort()
    deferred_ids.sort()
    entries = [
        Posting(account=p, asset=a, delta=d)
        for (p, a), d in sorted(net_delta.items())
        if d != 0
    ]
    if entries:
        post(view, entries)

    cycle_id = h("CLEARMESH/CYCLE/v1", height.to_bytes(8, "big"))
    receipts: list[Receipt] = []
    gross_by: dict[str, int] = {}
    liq_used_by: dict[str, int] = {}

    # per-participant liquidity used
    per_part_out: dict[tuple[str, str], int] = {}
    per_part_in: dict[tuple[str, str], int] = {}
    for uid in settled_ids:
        u = by_id[uid]
        for payer, payee, asset, amt in u["legs"]:
            gross_by[asset] = gross_by.get(asset, 0) + amt
            per_part_out[(payer, asset)] = per_part_out.get((payer, asset), 0) + amt
            per_part_in[(payee, asset)] = per_part_in.get((payee, asset), 0) + amt

    for (p, a), outv in per_part_out.items():
        used = outv - per_part_in.get((p, a), 0)
        if used > 0:
            liq_used_by[a] = liq_used_by.get(a, 0) + used

    for uid in settled_ids:
        u = by_id[uid]
        if u["kind"] == "single":
            instr = view.get_instruction(u["uetr"])
            assert instr is not None
            new_instr, receipt = transition(
                instr,
                "SETTLE",
                height=height,
                cause="CYCLE",
                cause_ref=cycle_id,
                method="NETTED",
                postings=tuple(
                    e
                    for e in entries
                    if e.account in (instr.debtor, instr.creditor) and e.asset == instr.asset
                ),
            )
            new_instr = replace(new_instr, cycle_id=cycle_id)
            view.put_instruction(new_instr)
            Q.remove(view, instr.debtor, instr.priority, instr.seq)
            receipts.append(receipt)
        else:
            g = view.get_group(u["id"])
            assert g is not None
            from clearmesh.types.records import GroupStatus

            view.put_group(replace(g, status="SETTLED"))
            # remove from gq
            for gk, gv in list(view.o.scan("gq/")):
                if gv.decode("utf-8") == u["id"].hex():
                    view.o.delete(gk)
            receipts.append(
                Receipt(
                    subject=u["id"].hex(),
                    from_status="ARMED",
                    to_status="SETTLED",
                    height=height,
                    cause="CYCLE",
                    cause_ref=cycle_id,
                    method="NETTED",
                    reason_code="OK",
                    postings=(),
                )
            )

    per_asset: list[AssetStat] = []
    for asset in sorted(set(gross_by) | set(liq_used_by)):
        gross = gross_by.get(asset, 0)
        liq = liq_used_by.get(asset, 0)
        lsr = 0 if gross == 0 else 10000 - (liq * 10000 // gross)
        per_asset.append(AssetStat(asset=asset, gross=gross, liquidity_used=liq, lsr_bps=lsr))

    report = NettingReport(
        cycle_id=cycle_id,
        height=height,
        settled=tuple(settled_ids),
        deferred=tuple(deferred_ids),
        per_asset=tuple(per_asset),
    )
    view.put_netting(report)
    return receipts, report


def _deactivate(active_ids: list[bytes], active_index: dict[bytes, int], uid: bytes) -> None:
    if uid not in active_index:
        return
    del active_index[uid]
