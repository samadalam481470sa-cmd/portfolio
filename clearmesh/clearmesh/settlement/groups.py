"""DvP / PvP settlement groups."""

from __future__ import annotations

from dataclasses import replace

from clearmesh.core.reasons import ReasonCode, TxReject
from clearmesh.state.world import WorldView
from clearmesh.types.records import Group, Leg
from clearmesh.types.tx import AffirmGroup, ProposeGroup, TxEnvelope, tx_id


def propose(view: WorldView, env: TxEnvelope, height: int) -> Group:
    body = env.body
    if not isinstance(body, ProposeGroup):
        raise TxReject(ReasonCode.FF01, "not propose group")
    if len(body.legs) < 2 or len(body.legs) > 8:
        raise TxReject(ReasonCode.FF01, "groups need 2..8 legs")
    legs = tuple(Leg(payer=a, payee=b, asset=c, amount=d) for a, b, c, d in body.legs)
    for leg in legs:
        if leg.amount <= 0 or leg.amount >= 2**63:
            raise TxReject(ReasonCode.FF01, "bad leg amount")
    payers = tuple(sorted({leg.payer for leg in legs}))
    if env.signer not in payers:
        raise TxReject(ReasonCode.BE05, "proposer must be a payer")
    gid = tx_id(env)
    seq = view.next_seq()
    g = Group(
        group_id=gid,
        legs=legs,
        required=payers,
        affirmed=(env.signer,),
        status="PENDING",
        priority=int(body.priority),
        admitted_height=height,
        seq=seq,
        expiry_height=body.expiry_height,
    )
    if set(g.affirmed) == set(g.required):
        g = replace(g, status="ARMED")
        view.o.put(f"gq/{g.priority:01d}{g.seq:020d}", g.group_id.hex().encode("utf-8"))
    view.put_group(g)
    view.o.put(f"x/{g.expiry_height:020d}/grp/{g.group_id.hex()}", b"")
    return g


def affirm(view: WorldView, env: TxEnvelope, height: int) -> Group:
    body = env.body
    if not isinstance(body, AffirmGroup):
        raise TxReject(ReasonCode.FF01, "not affirm")
    g = view.get_group(body.group_id)
    if g is None:
        raise TxReject(ReasonCode.FF01, "unknown group")
    if g.status != "PENDING":
        raise TxReject(ReasonCode.AG02, "group not pending")
    if env.signer not in g.required:
        raise TxReject(ReasonCode.BE05, "not a required payer")
    if env.signer in g.affirmed:
        raise TxReject(ReasonCode.DUPL, "already affirmed")
    affirmed = tuple(sorted(set(g.affirmed) | {env.signer}))
    status = "ARMED" if set(affirmed) == set(g.required) else "PENDING"
    g2 = replace(g, affirmed=affirmed, status=status)
    if status == "ARMED":
        view.o.put(f"gq/{g2.priority:01d}{g2.seq:020d}", g2.group_id.hex().encode("utf-8"))
    view.put_group(g2)
    return g2
