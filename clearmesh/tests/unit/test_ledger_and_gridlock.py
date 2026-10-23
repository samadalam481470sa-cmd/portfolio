"""Journal + gridlock scripted scenario."""

from __future__ import annotations

import tempfile
from pathlib import Path

from clearmesh.crypto.keys import Ed25519Signer
from clearmesh.execution.executor import apply_block
from clearmesh.ledger.journal import check_invariants
from clearmesh.node.genesis import (
    Genesis,
    GenesisParticipant,
    GenesisValidator,
    default_policy_dict,
    genesis_hash,
    init_genesis_state,
)
from clearmesh.state.overlay import Overlay
from clearmesh.state.store import Store
from clearmesh.state.world import WorldView
from clearmesh.types.block import Block, BlockHeader
from clearmesh.types.tx import (
    Issue,
    PaymentInstruction,
    Priority,
    Role,
    Sig,
    TxEnvelope,
    TxType,
    tx_id,
)
from clearmesh.crypto.keys import key_id
from clearmesh.crypto.envelope import generate_enc_keypair


def _genesis(tmp: Path) -> tuple[Genesis, dict[str, Ed25519Signer]]:
    keys: dict[str, Ed25519Signer] = {}
    parts = []
    vals = []
    for pid, roles in [
        ("SA", [Role.SA, Role.OPS, Role.VALIDATOR]),
        ("BANKA", [Role.OPS, Role.COMPLIANCE, Role.VALIDATOR]),
        ("BANKB", [Role.OPS, Role.COMPLIANCE, Role.VALIDATOR]),
        ("BANKC", [Role.OPS, Role.COMPLIANCE, Role.VALIDATOR]),
        ("BANKD", [Role.OPS, Role.COMPLIANCE]),
    ]:
        ops1 = Ed25519Signer()
        ops2 = Ed25519Signer()
        keys[f"{pid}_ops1"] = ops1
        keys[f"{pid}_ops2"] = ops2
        enc_priv, enc_pub = generate_enc_keypair()
        parts.append(
            GenesisParticipant(
                id=pid,
                lei=f"SIMCLEARMESH{pid:>08}"[:20],
                display_name=pid,
                roles=[int(r) for r in roles],
                ops_pubkeys_hex=[ops1.public_key.hex(), ops2.public_key.hex()],
                compliance_pubkeys_hex=[],
                enc_pubkey_hex=enc_pub.hex(),
            )
        )
        if Role.VALIDATOR in roles:
            node = Ed25519Signer()
            keys[f"{pid}_node"] = node
            vals.append(GenesisValidator(pid, node.public_key.hex(), 1))
    pol = default_policy_dict()
    pol["netting_interval_blocks"] = 2
    pol["maker_checker_threshold"] = 1  # always dual sig in this test
    g = Genesis(
        chain_id="clearmesh-sim-1",
        validators=vals,
        participants=parts,
        policy=pol,
        assets={"SIM": {"decimals": 2, "issuer_role": int(Role.SA)}, "TBOND": {"decimals": 0, "issuer_role": 5}},
    )
    g.save(tmp / "genesis.json")
    return g, keys


def _sign(body, tx_type, signer, key_list, height) -> TxEnvelope:
    env = TxEnvelope(1, "clearmesh-sim-1", int(tx_type), signer, height + 50, body, ())
    digest = tx_id(env)
    sigs = tuple(
        sorted(
            (Sig(key_id(k.public_key), k.sign(digest)) for k in key_list),
            key=lambda s: s.key_id,
        )
    )
    return TxEnvelope(1, "clearmesh-sim-1", int(tx_type), signer, height + 50, body, sigs)


def _block(height: int, txs: list[TxEnvelope], prev: bytes) -> Block:
    hdr = BlockHeader(
        version=1,
        chain_id="clearmesh-sim-1",
        height=height,
        round=0,
        time_ms=height * 1000,
        prev_block_hash=prev,
        last_commit_hash=b"\x00" * 32,
        tx_root=b"\x00" * 32,
        receipts_root=b"\x00" * 32,
        state_root=b"\x00" * 32,
        liabilities_root=b"\x00" * 32,
        validators_hash=b"\x00" * 32,
        policy_hash=b"\x00" * 32,
        sanctions_version=0,
        proposer_index=0,
    )
    return Block(header=hdr, txs=tuple(txs), last_commit=None)


def test_gridlock_circle() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g, keys = _genesis(tmp)
        store = Store.open(tmp / "db.sqlite")
        init_genesis_state(store, g)
        prev = genesis_hash(g)

        def commit(height: int, txs: list[TxEnvelope]) -> None:
            nonlocal prev
            overlay = Overlay(store)
            block = _block(height, txs, prev)
            result = apply_block(overlay, block, g.chain_id)
            from clearmesh.types.block import BlockHeader, block_hash
            from clearmesh.core.codec import encode
            from clearmesh.types.block import Commit, CommitSig

            hdr = BlockHeader(
                version=1,
                chain_id=g.chain_id,
                height=height,
                round=0,
                time_ms=height * 1000,
                prev_block_hash=prev,
                last_commit_hash=b"\x00" * 32,
                tx_root=result.roots["tx_root"],
                receipts_root=result.roots["receipts_root"],
                state_root=result.roots["state_root"],
                liabilities_root=result.roots["liabilities_root"],
                validators_hash=b"\x00" * 32,
                policy_hash=result.roots["policy_hash"],
                sanctions_version=0,
                proposer_index=0,
            )
            block = Block(header=hdr, txs=tuple(txs), last_commit=None)
            commit_obj = Commit(height, 0, block_hash(hdr), (CommitSig(0, b"\x00" * 64),))
            store.commit_block(
                height,
                encode(block),
                encode(commit_obj),
                encode(result.receipts),
                result.roots,
                result.writes,
                result.tx_ids,
            )
            prev = block_hash(hdr)

        # fund
        h = 1
        issues = []
        for bank, amt in [("BANKA", 10000), ("BANKB", 10000), ("BANKC", 10000), ("BANKD", 5000)]:
            issues.append(
                _sign(
                    Issue("SIM", bank, amt),
                    TxType.ISSUE,
                    "SA",
                    [keys["SA_ops1"], keys["SA_ops2"]],
                    h,
                )
            )
        commit(h, issues)

        import uuid

        def pay(debtor, creditor, amt, height):
            return _sign(
                PaymentInstruction(
                    kind="INTERBANK",
                    uetr=str(uuid.uuid4()),
                    end_to_end_id="e2e",
                    debtor=debtor,
                    creditor=creditor,
                    asset="SIM",
                    amount=amt,
                    priority=int(Priority.NORMAL),
                    settle_by_height=height + 100,
                    purpose_code="T",
                    envelope=None,
                    originator_attestation=None,
                ),
                TxType.PAYMENT_INSTRUCTION,
                debtor,
                [keys[f"{debtor}_ops1"], keys[f"{debtor}_ops2"]],
                height,
            )

        h = 2
        commit(
            h,
            [
                pay("BANKA", "BANKB", 50000, h),
                pay("BANKB", "BANKC", 50000, h),
                pay("BANKC", "BANKA", 50000, h),
                pay("BANKD", "BANKA", 30000, h),
            ],
        )
        # height 2 may net if interval=2
        world = WorldView(Overlay(store))
        assert check_invariants(world) == []
        # balances conserved
        total = sum(world.get_balance(b, "SIM") for b in ("BANKA", "BANKB", "BANKC", "BANKD"))
        assert total == 35000
        # D->A 300 should remain queued (D has 50)
        from clearmesh.settlement import queue as Q

        d_items = Q.items(world, "BANKD")
        assert len(d_items) == 1
