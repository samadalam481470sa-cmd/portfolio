"""apply_block(): the only state-transition entrypoint."""

from __future__ import annotations

from dataclasses import dataclass

from clearmesh.core.reasons import TxReject
from clearmesh.execution.handlers import handle_tx
from clearmesh.settlement.engine import begin_block, end_block
from clearmesh.state.overlay import Overlay
from clearmesh.state.roots import liabilities_root, policy_hash, receipts_root, state_root, tx_root
from clearmesh.state.world import WorldView
from clearmesh.types.block import Block
from clearmesh.types.receipt import Receipt
from clearmesh.types.records import NettingReport
from clearmesh.types.tx import TxEnvelope, tx_id


@dataclass(frozen=True, slots=True)
class ExecResult:
    writes: list[tuple[bytes, bytes | None]]
    receipts: list[Receipt]
    roots: dict[str, bytes]
    report: NettingReport | None
    tx_ids: list[bytes]


def check_stateless(env: TxEnvelope, chain_id: str, height: int, max_ttl: int) -> None:
    if env.version != 1:
        raise TxReject("FF01", "bad version")
    if env.chain_id != chain_id:
        raise TxReject("FF01", "wrong chain_id")
    if not (height < env.valid_until_height <= height + max_ttl):
        raise TxReject("TM01", "valid_until_height out of range")


def _verify_envelope_sigs(world: WorldView, env: TxEnvelope, height: int) -> None:
    """Verify Ed25519 sigs against signer OPS or COMPLIANCE keys (may be either)."""
    from clearmesh.crypto.keys import verify
    from clearmesh.types.tx import TxType

    part = world.get_participant(env.signer)
    if part is None or not part.active:
        raise TxReject("BE05", "unknown signer")
    if not env.sigs:
        raise TxReject("DS0H", "missing signatures")
    pubs: dict[bytes, bytes] = {}
    for kr in part.ops_keys:
        if kr.revoked_at is None or kr.revoked_at > height:
            pubs[kr.key_id] = kr.pubkey
    # Compliance may sign BENEFICIARY_SCREEN_RESULT / attest paths
    if TxType(env.tx_type) in (
        TxType.BENEFICIARY_SCREEN_RESULT,
        TxType.PUBLISH_SANCTIONS_LIST,
    ):
        for kr in part.compliance_keys:
            if kr.revoked_at is None or kr.revoked_at > height:
                pubs[kr.key_id] = kr.pubkey
        # screener uses ops
        for kr in part.ops_keys:
            if kr.revoked_at is None or kr.revoked_at > height:
                pubs[kr.key_id] = kr.pubkey
    digest = tx_id(env)
    seen: set[bytes] = set()
    for sig in env.sigs:
        if sig.key_id in seen:
            raise TxReject("DS04", "duplicate sig key")
        seen.add(sig.key_id)
        pub = pubs.get(sig.key_id)
        if pub is None or not verify(pub, digest, sig.sig):
            raise TxReject("DS0H", "bad envelope signature")


def apply_block(view: Overlay, block: Block, chain_id: str) -> ExecResult:
    world = WorldView(view)
    height = block.header.height
    receipts: list[Receipt] = []
    receipts.extend(begin_block(world, height))

    pol = world.get_policy()
    max_ttl = pol.max_tx_ttl if pol else 100
    tx_ids: list[bytes] = []

    for env in block.txs:
        if not isinstance(env, TxEnvelope):
            raise TxReject("FF01", "tx not TxEnvelope")
        check_stateless(env, chain_id, height, max_ttl)
        tid = tx_id(env)
        # seen window
        if world.o.get(f"seen/{env.valid_until_height:020d}/{tid.hex()}") is not None:
            raise TxReject("DUPL", "tx already seen")
        _verify_envelope_sigs(world, env, height)
        child = view.child()
        child_world = WorldView(child)
        try:
            recs = handle_tx(child_world, env, height)
        except TxReject:
            raise
        child.apply_to_parent()
        world.mark_seen(env.valid_until_height, tid)
        receipts.extend(recs)
        tx_ids.append(tid)

    end_recs, report = end_block(world, height)
    receipts.extend(end_recs)

    roots = {
        "tx_root": tx_root(list(block.txs)),
        "receipts_root": receipts_root(receipts),
        "state_root": state_root(view),
        "liabilities_root": liabilities_root(view),
        "policy_hash": policy_hash(view),
    }
    return ExecResult(
        writes=view.diff(),
        receipts=receipts,
        roots=roots,
        report=report,
        tx_ids=tx_ids,
    )
