"""Begin/end-block settlement: timeouts, gross pass, expiry, gridlock."""

from __future__ import annotations

from dataclasses import replace

from clearmesh.ledger.journal import post
from clearmesh.settlement import queue as Q
from clearmesh.settlement.gridlock import run as gridlock_run
from clearmesh.settlement.lifecycle import transition
from clearmesh.state.world import WorldView
from clearmesh.types.receipt import Posting, Receipt
from clearmesh.types.records import NettingReport


def begin_block(view: WorldView, height: int) -> list[Receipt]:
    receipts: list[Receipt] = []
    # Apply pending policy
    raw = view.o.get(f"pol_pending/{height}")
    if raw is not None:
        from clearmesh.core.codec import decode
        from clearmesh.types.records import Policy

        pol = decode(Policy, raw)
        view.put_policy(pol)
        view.o.delete(f"pol_pending/{height}")

    # Drain expiry index due at height
    prefix = f"x/{height:020d}/"
    due = list(view.o.scan(prefix))
    for k, _ in due:
        parts = k.decode("utf-8").split("/")
        # x/{h}/{kind}/{id}
        if len(parts) < 4:
            view.o.delete(k)
            continue
        kind, ident = parts[2], parts[3]
        if kind == "screen":
            instr = view.get_instruction(ident)
            if instr and instr.status == "AWAITING_BENEFICIARY_SCREEN":
                new_i, rec = transition(
                    instr, "TIMEOUT", height=height, cause="ENGINE", cause_ref=b""
                )
                view.put_instruction(new_i)
                receipts.append(rec)
        elif kind == "instr":
            instr = view.get_instruction(ident)
            if instr and instr.status == "QUEUED":
                Q.remove(view, instr.debtor, instr.priority, instr.seq)
                new_i, rec = transition(
                    instr, "EXPIRE", height=height, cause="ENGINE", cause_ref=b""
                )
                view.put_instruction(new_i)
                receipts.append(rec)
        elif kind == "grp":
            gid = bytes.fromhex(ident)
            g = view.get_group(gid)
            if g and g.status in ("PENDING", "ARMED"):
                view.put_group(replace(g, status="EXPIRED"))
                for gk, gv in list(view.o.scan("gq/")):
                    if gv.decode("utf-8") == ident:
                        view.o.delete(gk)
                receipts.append(
                    Receipt(
                        subject=ident,
                        from_status=g.status,
                        to_status="EXPIRED",
                        height=height,
                        cause="ENGINE",
                        cause_ref=b"",
                        method="NONE",
                        reason_code="AM04",
                        postings=(),
                    )
                )
        view.o.delete(k)

    # Prune seen/ with valid_until < height
    for k, _ in list(view.o.scan("seen/")):
        # seen/{valid_until:020}/{tx_id}
        parts = k.decode("utf-8").split("/")
        if len(parts) >= 2:
            try:
                vu = int(parts[1])
            except ValueError:
                continue
            if vu < height:
                view.o.delete(k)
    return receipts


def _settle_instruction(view: WorldView, uetr: str, height: int, method: str) -> Receipt | None:
    instr = view.get_instruction(uetr)
    if instr is None or instr.status != "QUEUED":
        return None
    d_acct = view.get_account(instr.debtor)
    c_acct = view.get_account(instr.creditor)
    if (d_acct and d_acct.frozen) or (c_acct and c_acct.frozen):
        return None
    if view.get_balance(instr.debtor, instr.asset) < instr.amount:
        return None
    entries = [
        Posting(account=instr.debtor, asset=instr.asset, delta=-instr.amount),
        Posting(account=instr.creditor, asset=instr.asset, delta=instr.amount),
    ]
    post(view, entries)
    Q.remove(view, instr.debtor, instr.priority, instr.seq)
    new_i, rec = transition(
        instr,
        "SETTLE",
        height=height,
        cause="ENGINE",
        cause_ref=b"",
        method=method,
        postings=tuple(entries),
    )
    view.put_instruction(new_i)
    return rec


def _try_group_gross(view: WorldView, height: int) -> list[Receipt]:
    receipts: list[Receipt] = []
    armed: list[tuple[bytes, object]] = []
    for k, v in view.o.scan("gq/"):
        gid = bytes.fromhex(v.decode("utf-8"))
        g = view.get_group(gid)
        if g and g.status == "ARMED":
            armed.append((gid, g))
    for gid, g in armed:
        # net debit per payer/asset within group
        net: dict[tuple[str, str], int] = {}
        for leg in g.legs:
            net[(leg.payer, leg.asset)] = net.get((leg.payer, leg.asset), 0) - leg.amount
            net[(leg.payee, leg.asset)] = net.get((leg.payee, leg.asset), 0) + leg.amount
        ok = True
        for (p, a), d in net.items():
            if d < 0 and view.get_balance(p, a) < -d:
                ok = False
                break
            acct = view.get_account(p)
            if acct and acct.frozen:
                ok = False
                break
        if not ok:
            continue
        entries = [Posting(account=p, asset=a, delta=d) for (p, a), d in sorted(net.items()) if d != 0]
        post(view, entries)
        view.put_group(replace(g, status="SETTLED"))
        for gk, gv in list(view.o.scan("gq/")):
            if gv.decode("utf-8") == gid.hex():
                view.o.delete(gk)
        receipts.append(
            Receipt(
                subject=gid.hex(),
                from_status="ARMED",
                to_status="SETTLED",
                height=height,
                cause="ENGINE",
                cause_ref=b"",
                method="GROSS",
                reason_code="OK",
                postings=tuple(entries),
            )
        )
    return receipts


def end_block(view: WorldView, height: int) -> tuple[list[Receipt], NettingReport | None]:
    receipts: list[Receipt] = []
    # 1. Gross pass
    progress = True
    while progress:
        progress = False
        for debtor in Q.all_debtors(view):
            h = Q.head(view, debtor)
            if h is None:
                continue
            uetr, _, _ = h
            rec = _settle_instruction(view, uetr, height, "GROSS")
            if rec is not None:
                receipts.append(rec)
                progress = True

    # 2. Armed groups gross
    receipts.extend(_try_group_gross(view, height))

    # 3. Gridlock
    report = None
    pol = view.get_policy()
    if pol and pol.netting_interval_blocks > 0 and height % pol.netting_interval_blocks == 0:
        greceipts, report = gridlock_run(view, height)
        receipts.extend(greceipts)
    return receipts, report
