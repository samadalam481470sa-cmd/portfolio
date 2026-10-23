"""Generate keys, genesis, certs, compose files for a local testnet."""

from __future__ import annotations

import json
from pathlib import Path

from clearmesh.compliance.sanctions_list import (
    content_hash,
    default_synthetic_list,
    list_merkle_root,
)
from clearmesh.crypto.envelope import generate_enc_keypair
from clearmesh.crypto.keys import Ed25519Signer
from clearmesh.crypto.keystore import save_keystore
from clearmesh.node.genesis import Genesis, GenesisParticipant, GenesisValidator, default_policy_dict
from clearmesh.types.tx import Role


def _lei(n: int) -> str:
    # Synthetic 20-char LEI-like id (mod97 not required for demo genesis)
    return f"SIMCLEARMESH{n:08d}"[:20]


def generate_testnet(out: Path, banks: int = 4, password: str = "testnet") -> Genesis:
    out.mkdir(parents=True, exist_ok=True)
    keys_dir = out / "keys"
    keys_dir.mkdir(exist_ok=True)

    bank_ids = [f"BANK{chr(65+i)}" for i in range(banks)]
    # BANKA,B,C validators + SA; BANKD non-validator if banks>=4
    validators_banks = bank_ids[:3]
    participants: list[GenesisParticipant] = []
    validators: list[GenesisValidator] = []

    # Settlement Agent
    sa_node = Ed25519Signer()
    sa_ops = Ed25519Signer()
    sa_gov = Ed25519Signer()
    sa_enc_priv, sa_enc_pub = generate_enc_keypair()
    save_keystore(keys_dir / "SA_node.key", sa_node.seed, password)
    save_keystore(keys_dir / "SA_ops.key", sa_ops.seed, password)
    save_keystore(keys_dir / "SA_gov.key", sa_gov.seed, password)
    (keys_dir / "SA_enc.priv").write_bytes(sa_enc_priv)
    participants.append(
        GenesisParticipant(
            id="SA",
            lei=_lei(0),
            display_name="Settlement Agent",
            roles=[int(Role.SA), int(Role.GOV), int(Role.VALIDATOR), int(Role.OPS)],
            ops_pubkeys_hex=[sa_ops.public_key.hex()],
            compliance_pubkeys_hex=[],
            enc_pubkey_hex=sa_enc_pub.hex(),
        )
    )
    validators.append(
        GenesisValidator(participant_id="SA", pubkey_hex=sa_node.public_key.hex(), power=1)
    )

    # CSD
    csd_ops = Ed25519Signer()
    csd_enc_priv, csd_enc_pub = generate_enc_keypair()
    save_keystore(keys_dir / "CSD_ops.key", csd_ops.seed, password)
    (keys_dir / "CSD_enc.priv").write_bytes(csd_enc_priv)
    participants.append(
        GenesisParticipant(
            id="CSD",
            lei=_lei(99),
            display_name="Securities Depository",
            roles=[int(Role.CSD), int(Role.OPS)],
            ops_pubkeys_hex=[csd_ops.public_key.hex()],
            compliance_pubkeys_hex=[],
            enc_pubkey_hex=csd_enc_pub.hex(),
        )
    )

    # Screening utility + Auditor
    scr = Ed25519Signer()
    aud_ops = Ed25519Signer()
    aud_enc_priv, aud_enc_pub = generate_enc_keypair()
    save_keystore(keys_dir / "SCREENER_ops.key", scr.seed, password)
    save_keystore(keys_dir / "AUDITOR_ops.key", aud_ops.seed, password)
    (keys_dir / "AUDITOR_enc.priv").write_bytes(aud_enc_priv)
    participants.append(
        GenesisParticipant(
            id="SCREENER",
            lei=_lei(98),
            display_name="Screening Utility",
            roles=[int(Role.SCREENER), int(Role.OPS)],
            ops_pubkeys_hex=[scr.public_key.hex()],
            compliance_pubkeys_hex=[],
            enc_pubkey_hex=generate_enc_keypair()[1].hex(),
        )
    )
    participants.append(
        GenesisParticipant(
            id="AUDITOR",
            lei=_lei(97),
            display_name="Auditor",
            roles=[int(Role.AUDITOR), int(Role.OPS)],
            ops_pubkeys_hex=[aud_ops.public_key.hex()],
            compliance_pubkeys_hex=[],
            enc_pubkey_hex=aud_enc_pub.hex(),
        )
    )

    for i, bid in enumerate(bank_ids):
        node = Ed25519Signer()
        ops1 = Ed25519Signer()
        ops2 = Ed25519Signer()
        comp = Ed25519Signer()
        enc_priv, enc_pub = generate_enc_keypair()
        save_keystore(keys_dir / f"{bid}_node.key", node.seed, password)
        save_keystore(keys_dir / f"{bid}_ops1.key", ops1.seed, password)
        save_keystore(keys_dir / f"{bid}_ops2.key", ops2.seed, password)
        save_keystore(keys_dir / f"{bid}_compliance.key", comp.seed, password)
        (keys_dir / f"{bid}_enc.priv").write_bytes(enc_priv)
        roles = [int(Role.OPS), int(Role.COMPLIANCE)]
        if bid in validators_banks:
            roles.append(int(Role.VALIDATOR))
            validators.append(
                GenesisValidator(participant_id=bid, pubkey_hex=node.public_key.hex(), power=1)
            )
        participants.append(
            GenesisParticipant(
                id=bid,
                lei=_lei(i + 1),
                display_name=f"Synthetic Bank {bid}",
                roles=roles,
                ops_pubkeys_hex=[ops1.public_key.hex(), ops2.public_key.hex()],
                compliance_pubkeys_hex=[comp.public_key.hex()],
                enc_pubkey_hex=enc_pub.hex(),
            )
        )

    genesis = Genesis(
        chain_id="clearmesh-sim-1",
        validators=validators,  # SA + BANKA/B/C = 4
        participants=participants,
        policy=default_policy_dict(),
        assets={
            "SIM": {"decimals": 2, "issuer_role": int(Role.SA)},
            "TBOND": {"decimals": 0, "issuer_role": int(Role.CSD)},
        },
    )
    genesis.save(out / "genesis.json")

    # Solo node config (primary demo path)
    node_toml = f"""chain_id = "clearmesh-sim-1"
data_dir = "{(out / 'data').as_posix()}"
genesis_path = "{(out / 'genesis.json').as_posix()}"
listen_host = "127.0.0.1"
listen_port = 26656
rpc_host = "127.0.0.1"
rpc_port = 26657
validator_key_path = "{(keys_dir / 'SA_node.key').as_posix()}"
solo = true
block_interval_s = 0.5
demo_evil_rpc = false
peers = []
"""
    (out / "node.toml").write_text(node_toml, encoding="utf-8")

    # Sanctions sample meta
    entries = default_synthetic_list()
    meta = {
        "version": 1,
        "merkle_root": list_merkle_root(entries).hex(),
        "content_hash": content_hash(entries).hex(),
        "entry_count": len(entries),
        "effective_height": 1,
        "entries": [
            {"id": e.entry_id, "name": e.name, "aliases": list(e.aliases)} for e in entries
        ],
    }
    (out / "sanctions_v1.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    compose = """services:
  clearmesh-solo:
    build: ..
    command: ["clearmesh", "node", "start", "--config", "/testnet/node.toml", "--password", "testnet"]
    volumes:
      - ./:/testnet
    ports:
      - "26657:26657"
    environment:
      - CLEARMESH_PASSWORD=testnet
"""
    (out / "docker-compose.yml").write_text(compose, encoding="utf-8")
    return genesis
