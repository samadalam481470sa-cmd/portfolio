"""Genesis type and state initialization. genesis_hash is the root of trust."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from clearmesh.core.codec import encode
from clearmesh.crypto.hashing import h
from clearmesh.crypto.keys import key_id
from clearmesh.state.overlay import Overlay
from clearmesh.state.store import Store
from clearmesh.types.records import Account, AssetMeta, KeyRec, Participant, Policy
from clearmesh.types.tx import Role


@dataclass
class GenesisValidator:
    participant_id: str
    pubkey_hex: str
    power: int = 1


@dataclass
class GenesisParticipant:
    id: str
    lei: str
    display_name: str
    roles: list[int]
    ops_pubkeys_hex: list[str]
    compliance_pubkeys_hex: list[str]
    enc_pubkey_hex: str


@dataclass
class Genesis:
    chain_id: str
    validators: list[GenesisValidator]
    participants: list[GenesisParticipant]
    policy: dict
    assets: dict  # asset -> {decimals, issuer_role}

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    @staticmethod
    def from_json(text: str) -> Genesis:
        d = json.loads(text)
        return Genesis(
            chain_id=d["chain_id"],
            validators=[GenesisValidator(**v) for v in d["validators"]],
            participants=[GenesisParticipant(**p) for p in d["participants"]],
            policy=d["policy"],
            assets=d["assets"],
        )

    @staticmethod
    def load(path: str | Path) -> Genesis:
        return Genesis.from_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")


def genesis_hash(g: Genesis) -> bytes:
    return h("CLEARMESH/LEAF/v1", g.to_json().encode("utf-8"))


def init_genesis_state(store: Store, g: Genesis) -> None:
    """Write genesis participants/policy/assets at height 0 (no block)."""
    if store.last_height() != 0:
        return
    # Use direct kv writes via a synthetic commit at height 0? Outline uses genesis load.
    # We'll put keys without a block using a one-shot transaction.
    overlay = Overlay(store)
    from clearmesh.state.world import WorldView

    world = WorldView(overlay)
    pol = Policy(
        maker_checker_threshold=int(g.policy.get("maker_checker_threshold", 100000)),
        netting_interval_blocks=int(g.policy.get("netting_interval_blocks", 5)),
        beneficiary_screen_timeout_blocks=int(
            g.policy.get("beneficiary_screen_timeout_blocks", 20)
        ),
        list_grace_blocks=int(g.policy.get("list_grace_blocks", 10)),
        max_tx_per_block=int(g.policy.get("max_tx_per_block", 100)),
        max_tx_ttl=int(g.policy.get("max_tx_ttl", 100)),
        max_queue_units=int(g.policy.get("max_queue_units", 10000)),
        redeem_sa_threshold=int(g.policy.get("redeem_sa_threshold", 1000000)),
    )
    world.put_policy(pol)
    for aid, meta in g.assets.items():
        world.put_asset(
            aid,
            AssetMeta(
                decimals=int(meta["decimals"]),
                issuer_role=int(meta["issuer_role"]),
                total_supply=0,
            ),
        )
    for p in g.participants:
        ops = tuple(
            KeyRec(key_id=key_id(bytes.fromhex(pk)), pubkey=bytes.fromhex(pk), revoked_at=None)
            for pk in p.ops_pubkeys_hex
        )
        comp = tuple(
            KeyRec(key_id=key_id(bytes.fromhex(pk)), pubkey=bytes.fromhex(pk), revoked_at=None)
            for pk in p.compliance_pubkeys_hex
        )
        world.put_participant(
            Participant(
                id=p.id,
                lei=p.lei,
                display_name=p.display_name,
                roles=tuple(p.roles),
                ops_keys=ops,
                compliance_keys=comp,
                enc_pubkey=bytes.fromhex(p.enc_pubkey_hex),
                active=True,
            )
        )
        world.put_account(
            p.id, Account(frozen=False, freeze_case_hash=b"\x00" * 32, debit_caps=())
        )

    # Persist overlay diff as height-0 meta bootstrap (not a consensus block)
    c = store._conn
    c.execute("BEGIN IMMEDIATE")
    try:
        for k, v in overlay.diff():
            if v is None:
                c.execute("DELETE FROM kv WHERE k = ?", (k,))
            else:
                c.execute(
                    "INSERT INTO kv(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                    (k, v),
                )
        c.execute(
            "INSERT INTO meta(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            ("last_height", (0).to_bytes(8, "big")),
        )
        c.execute(
            "INSERT INTO meta(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            ("genesis_hash", genesis_hash(g)),
        )
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise


def default_policy_dict() -> dict:
    return {
        "maker_checker_threshold": 100_00,  # 100.00 SIM
        "netting_interval_blocks": 5,
        "beneficiary_screen_timeout_blocks": 20,
        "list_grace_blocks": 10,
        "max_tx_per_block": 100,
        "max_tx_ttl": 100,
        "max_queue_units": 10000,
        "redeem_sa_threshold": 1_000_000_00,
    }
