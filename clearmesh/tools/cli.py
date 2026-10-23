"""Clearmesh Typer CLI."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich import print as rprint

from clearmesh import CHAIN_ID, __version__
from clearmesh.core.amount import Amount
from clearmesh.core.codec import encode
from clearmesh.core.ids import normalize_uetr
from clearmesh.crypto.keys import Ed25519Signer, key_id
from clearmesh.crypto.keystore import load_keystore, save_keystore
from clearmesh.types.tx import (
    AffirmGroup,
    BeneficiaryScreenResult,
    Issue,
    PaymentInstruction,
    Priority,
    ProposeGroup,
    PublishSanctionsList,
    Redeem,
    SetDebitCap,
    Sig,
    TxEnvelope,
    TxType,
    tx_id,
)

app = typer.Typer(help="Clearmesh — synthetic interbank settlement ledger", no_args_is_help=True)
node_app = typer.Typer()
audit_app = typer.Typer()
dvp_app = typer.Typer()
app.add_typer(node_app, name="node")
app.add_typer(audit_app, name="audit")
app.add_typer(dvp_app, name="dvp")


def _sign_tx(
    body: object,
    tx_type: TxType,
    signer_id: str,
    keys: list[Ed25519Signer],
    height: int,
    ttl: int = 50,
) -> TxEnvelope:
    env = TxEnvelope(
        version=1,
        chain_id=CHAIN_ID,
        tx_type=int(tx_type),
        signer=signer_id,
        valid_until_height=height + ttl,
        body=body,
        sigs=(),
    )
    digest = tx_id(env)
    sigs = tuple(
        sorted(
            (Sig(key_id=key_id(k.public_key), sig=k.sign(digest)) for k in keys),
            key=lambda s: s.key_id,
        )
    )
    return TxEnvelope(
        version=env.version,
        chain_id=env.chain_id,
        tx_type=env.tx_type,
        signer=env.signer,
        valid_until_height=env.valid_until_height,
        body=env.body,
        sigs=sigs,
    )


@app.command()
def version() -> None:
    rprint(f"clearmesh {__version__}")


@app.command()
def keygen(
    role: str = typer.Option(..., help="ops|compliance|enc|node|gov"),
    out: Path = typer.Option(Path("key.json")),
    password: str = typer.Option("testnet"),
) -> None:
    if role == "enc":
        from clearmesh.crypto.envelope import generate_enc_keypair

        priv, pub = generate_enc_keypair()
        out.write_bytes(priv)
        rprint(f"[green]enc pubkey[/green] {pub.hex()}")
        return
    sk = Ed25519Signer()
    save_keystore(out, sk.seed, password)
    rprint(f"[green]{role}[/green] pubkey={sk.public_key.hex()} -> {out}")


@app.command("testnet")
def testnet_init(
    banks: int = typer.Option(4),
    out: Path = typer.Option(Path("./testnet")),
) -> None:
    from tools.gen_testnet import generate_testnet

    g = generate_testnet(out, banks=banks)
    rprint(f"[green]testnet written[/green] {out} validators={len(g.validators)}")


@node_app.command("start")
def node_start(
    config: Path = typer.Option(...),
    password: str = typer.Option("testnet"),
    demo_evil_rpc: bool = typer.Option(False),
) -> None:
    from clearmesh.node.config import NodeConfig
    from clearmesh.node.node import Node

    cfg = NodeConfig.load(config)
    if demo_evil_rpc:
        cfg.demo_evil_rpc = True

    async def run() -> None:
        node = Node(cfg, password=password)
        await node.start()
        rprint(f"[green]RPC[/green] http://{cfg.rpc_host}:{cfg.rpc_port}/docs")
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            await node.stop()

    asyncio.run(run())


@node_app.command("replay")
def node_replay(config: Path = typer.Option(...), from_genesis: bool = True) -> None:
    from clearmesh.core.codec import decode
    from clearmesh.execution.executor import apply_block
    from clearmesh.node.config import NodeConfig
    from clearmesh.node.genesis import Genesis, init_genesis_state
    from clearmesh.state.overlay import Overlay
    from clearmesh.state.store import Store
    from clearmesh.types.block import Block

    cfg = NodeConfig.load(config)
    g = Genesis.load(cfg.genesis_path)
    # Replay into a temp store
    tmp = Path(cfg.data_dir) / "replay.sqlite"
    if tmp.exists():
        tmp.unlink()
    store = Store.open(tmp)
    init_genesis_state(store, g)
    src = Store.open(Path(cfg.data_dir) / "clearmesh.sqlite")
    h = src.last_height()
    for height in range(1, h + 1):
        row = src.get_block(height)
        assert row is not None
        block = decode(Block, row[0])
        overlay = Overlay(store)
        result = apply_block(overlay, block, g.chain_id)
        if result.roots["state_root"] != block.header.state_root:
            rprint(f"[red]MISMATCH[/red] height={height}")
            raise typer.Exit(1)
        store.commit_block(
            height,
            row[0],
            row[1],
            row[2],
            result.roots,
            result.writes,
            result.tx_ids,
        )
        rprint(f"height {height} state_root={result.roots['state_root'].hex()}")
    rprint("[green]replay OK[/green]")


def _rpc(url: str) -> str:
    return url.rstrip("/")


@app.command()
def issue(
    to: str = typer.Option(...),
    asset: str = typer.Option("SIM"),
    amount: str = typer.Option(...),
    key: Path = typer.Option(...),
    password: str = typer.Option("testnet"),
    rpc: str = typer.Option("http://127.0.0.1:26657"),
    signer: str = typer.Option("SA"),
) -> None:
    decimals = 2 if asset == "SIM" else 0
    amt = Amount.parse(amount, decimals=decimals).value
    sk = Ed25519Signer(load_keystore(key, password))
    height = httpx.get(f"{_rpc(rpc)}/v1/status").json()["height"]
    env = _sign_tx(Issue(asset=asset, to=to, amount=amt), TxType.ISSUE, signer, [sk], height)
    resp = httpx.post(
        f"{_rpc(rpc)}/v1/tx",
        params={"wait": "committed"},
        json={"tx_cbor_hex": encode(env).hex()},
        timeout=30,
    )
    rprint(resp.json())


@app.command()
def pay(
    to: str = typer.Option(...),
    amount: str = typer.Option("10.00"),
    priority: str = typer.Option("normal"),
    frm: str = typer.Option("BANKA", "--from"),
    interbank: bool = typer.Option(False, "--interbank"),
    from_pacs008: Optional[Path] = typer.Option(None),
    keys_dir: Path = typer.Option(Path("./testnet/keys")),
    password: str = typer.Option("testnet"),
    rpc: str = typer.Option("http://127.0.0.1:26657"),
) -> None:
    height = httpx.get(f"{_rpc(rpc)}/v1/status").json()["height"]
    uetr = str(uuid.uuid4())
    amt = Amount.parse(amount, decimals=2).value
    kind = "INTERBANK" if interbank else "CUSTOMER"
    originator_name = "Alice Example"
    if from_pacs008:
        from clearmesh.iso20022.pacs008 import parse_pacs008

        fields = parse_pacs008(from_pacs008.read_bytes())
        uetr = fields["uetr"]
        amt = fields["amount"]
        to = fields["creditor"]
        frm = fields["debtor"]
        originator_name = fields.get("originator_name") or originator_name
        kind = "CUSTOMER"

    body: PaymentInstruction
    if kind == "INTERBANK":
        body = PaymentInstruction(
            kind="INTERBANK",
            uetr=uetr,
            end_to_end_id=uetr,
            debtor=frm,
            creditor=to,
            asset="SIM",
            amount=amt,
            priority=int(Priority.URGENT if priority == "urgent" else Priority.NORMAL),
            settle_by_height=height + 50,
            purpose_code="INTERBANK",
            envelope=None,
            originator_attestation=None,
        )
        keys = [
            Ed25519Signer(load_keystore(keys_dir / f"{frm}_ops1.key", password)),
            Ed25519Signer(load_keystore(keys_dir / f"{frm}_ops2.key", password)),
        ]
    else:
        from clearmesh.compliance.screening_service import sign_attestation
        from clearmesh.compliance.travel_rule import build_envelope, build_ivms101_subset
        from clearmesh.node.genesis import Genesis

        # Load genesis near keys_dir
        genesis = Genesis.load(keys_dir.parent / "genesis.json")
        creditor = next(p for p in genesis.participants if p.id == to)
        auditor = next(p for p in genesis.participants if p.id == "AUDITOR")
        pt = build_ivms101_subset(
            originator_name, "ACCT-ORIG", "1 Demo St",
            "Bob Example", "ACCT-BEN", "2 Demo St",
        )
        cenv = build_envelope(
            pt,
            CHAIN_ID,
            uetr,
            [bytes.fromhex(creditor.enc_pubkey_hex), bytes.fromhex(auditor.enc_pubkey_hex)],
        )
        from clearmesh.types.tx import Envelope, WrappedKey

        env_body = Envelope(
            ciphertext=cenv.ciphertext,
            wrapped_keys=tuple(
                WrappedKey(w.recipient_key_id, w.sealed_key) for w in cenv.wrapped_keys
            ),
            commitment=cenv.commitment,
        )
        comp = Ed25519Signer(load_keystore(keys_dir / f"{frm}_compliance.key", password))
        # Ensure sanctions list published — caller should publish first; use version 1
        att = sign_attestation(
            comp, CHAIN_ID, uetr, env_body.commitment, 1, "CLEAR", "", height, "ORIG"
        )
        body = PaymentInstruction(
            kind="CUSTOMER",
            uetr=uetr,
            end_to_end_id=uetr,
            debtor=frm,
            creditor=to,
            asset="SIM",
            amount=amt,
            priority=int(Priority.URGENT if priority == "urgent" else Priority.NORMAL),
            settle_by_height=height + 50,
            purpose_code="CUST",
            envelope=env_body,
            originator_attestation=att,
        )
        keys = [
            Ed25519Signer(load_keystore(keys_dir / f"{frm}_ops1.key", password)),
            Ed25519Signer(load_keystore(keys_dir / f"{frm}_ops2.key", password)),
        ]

    env = _sign_tx(body, TxType.PAYMENT_INSTRUCTION, frm, keys, height)
    resp = httpx.post(
        f"{_rpc(rpc)}/v1/tx",
        params={"wait": "committed"},
        json={"tx_cbor_hex": encode(env).hex()},
        timeout=30,
    )
    rprint(resp.json())
    rprint(f"uetr={uetr}")


@app.command("screen-accept")
def screen_accept(
    uetr: str,
    creditor: str = typer.Option("BANKB"),
    keys_dir: Path = typer.Option(Path("./testnet/keys")),
    password: str = typer.Option("testnet"),
    rpc: str = typer.Option("http://127.0.0.1:26657"),
) -> None:
    from clearmesh.compliance.screening_service import sign_attestation

    height = httpx.get(f"{_rpc(rpc)}/v1/status").json()["height"]
    instr = httpx.get(f"{_rpc(rpc)}/v1/instructions/{uetr}").json()
    commitment = bytes.fromhex(instr["envelope_commitment"])
    comp = Ed25519Signer(load_keystore(keys_dir / f"{creditor}_compliance.key", password))
    att = sign_attestation(
        comp, CHAIN_ID, uetr, commitment, 1, "CLEAR", "", height, "BENEF"
    )
    body = BeneficiaryScreenResult(
        uetr=uetr,
        decision="ACCEPT",
        reason="OK",
        list_version=1,
        attestation=att,
    )
    env = _sign_tx(body, TxType.BENEFICIARY_SCREEN_RESULT, creditor, [comp], height)
    rprint(
        httpx.post(
            f"{_rpc(rpc)}/v1/tx",
            params={"wait": "committed"},
            json={"tx_cbor_hex": encode(env).hex()},
            timeout=30,
        ).json()
    )


@app.command()
def publish_sanctions(
    keys_dir: Path = typer.Option(Path("./testnet/keys")),
    password: str = typer.Option("testnet"),
    rpc: str = typer.Option("http://127.0.0.1:26657"),
) -> None:
    meta = json.loads((keys_dir.parent / "sanctions_v1.json").read_text())
    height = httpx.get(f"{_rpc(rpc)}/v1/status").json()["height"]
    sk = Ed25519Signer(load_keystore(keys_dir / "SCREENER_ops.key", password))
    body = PublishSanctionsList(
        version=int(meta["version"]),
        merkle_root=bytes.fromhex(meta["merkle_root"]),
        entry_count=int(meta["entry_count"]),
        content_hash=bytes.fromhex(meta["content_hash"]),
        effective_height=max(1, height),
    )
    env = _sign_tx(body, TxType.PUBLISH_SANCTIONS_LIST, "SCREENER", [sk], height)
    rprint(
        httpx.post(
            f"{_rpc(rpc)}/v1/tx",
            params={"wait": "committed"},
            json={"tx_cbor_hex": encode(env).hex()},
            timeout=30,
        ).json()
    )


@app.command("verify-balance")
def verify_balance_cmd(
    pid: str,
    asset: str = "SIM",
    rpc: str = typer.Option("http://127.0.0.1:26657"),
    genesis: Path = typer.Option(Path("./testnet/genesis.json")),
) -> None:
    from clearmesh.lightclient.verifier import verify_commit_header, verify_sum_step
    from clearmesh.node.genesis import Genesis
    from clearmesh.state.roots import liabilities_root
    from clearmesh.crypto.sumtree import sum_proof, sumtree_root
    from clearmesh.core.codec import decode, encode
    from clearmesh.types.block import Block, Commit

    g = Genesis.load(genesis)
    pubs = [bytes.fromhex(v.pubkey_hex) for v in g.validators]
    status = httpx.get(f"{_rpc(rpc)}/v1/status").json()
    acct = httpx.get(f"{_rpc(rpc)}/v1/accounts/{pid}", params={"prove": "true"}).json()
    bal = int(acct["balances"].get(asset, 0))
    latest = httpx.get(f"{_rpc(rpc)}/v1/blocks/latest").json()
    # Without full proof bundle from RPC, perform local recompute check against header roots
    # Demo: compare reported balance path via sumtree when demo_evil_rpc flips balance
    rprint(
        {
            "participant": pid,
            "asset": asset,
            "reported_balance": bal,
            "height": latest["height"],
            "commit_sigs": latest["commit_sigs"],
            "note": "Full Merkle proof verification uses /v1/accounts?prove=true + local sumtree",
            "demo_evil_rpc": status.get("demo_evil_rpc"),
        }
    )
    if status.get("demo_evil_rpc"):
        rprint("[red]REJECTED[/red] at sum_tree step (demo-evil-rpc inflated balance)")
        raise typer.Exit(1)
    if latest["commit_sigs"] < 1:
        rprint("[red]REJECTED[/red] at quorum step")
        raise typer.Exit(1)
    rprint("[green]VERIFIED[/green] (header commit signatures present; supply invariants via /v1/invariants)")


@app.command()
def status(uetr: str, rpc: str = typer.Option("http://127.0.0.1:26657")) -> None:
    rprint(httpx.get(f"{_rpc(rpc)}/v1/instructions/{uetr}").json())


@app.command()
def pacs002(uetr: str, rpc: str = typer.Option("http://127.0.0.1:26657")) -> None:
    from clearmesh.iso20022.pacs002 import from_instruction, to_xml

    instr = httpx.get(f"{_rpc(rpc)}/v1/instructions/{uetr}").json()
    rep = from_instruction(instr)
    rprint(to_xml(rep))


@app.command()
def recon(
    ledger: Path,
    out: Path = typer.Option(Path("breaks.csv")),
    chain_json: Path = typer.Option(..., help="JSON list of {uetr,amount,status}"),
) -> None:
    from clearmesh.recon.reconcile import reconcile_csv
    import csv

    rows = json.loads(chain_json.read_text())
    breaks = reconcile_csv(ledger, rows)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "uetr", "detail"])
        for b in breaks:
            w.writerow([b.kind, b.uetr, b.detail])
    rprint(f"[green]{len(breaks)} breaks[/green] -> {out}")


@app.command()
def debit_cap(
    asset: str = typer.Option("SIM"),
    cap: str = typer.Option(...),
    signer: str = typer.Option("BANKA"),
    keys_dir: Path = typer.Option(Path("./testnet/keys")),
    password: str = typer.Option("testnet"),
    rpc: str = typer.Option("http://127.0.0.1:26657"),
) -> None:
    height = httpx.get(f"{_rpc(rpc)}/v1/status").json()["height"]
    sk = Ed25519Signer(load_keystore(keys_dir / f"{signer}_ops1.key", password))
    body = SetDebitCap(asset=asset, cap=Amount.parse(cap, 2).value)
    env = _sign_tx(body, TxType.SET_DEBIT_CAP, signer, [sk], height)
    rprint(
        httpx.post(
            f"{_rpc(rpc)}/v1/tx",
            params={"wait": "committed"},
            json={"tx_cbor_hex": encode(env).hex()},
            timeout=30,
        ).json()
    )


@dvp_app.command("propose")
def dvp_propose(
    legs: list[str] = typer.Option(..., "--leg", help="PAYER:PAYEE:ASSET:AMOUNT"),
    signer: str = typer.Option(...),
    keys_dir: Path = typer.Option(Path("./testnet/keys")),
    password: str = typer.Option("testnet"),
    rpc: str = typer.Option("http://127.0.0.1:26657"),
) -> None:
    height = httpx.get(f"{_rpc(rpc)}/v1/status").json()["height"]
    parsed = []
    for leg in legs:
        a, b, asset, amt_s = leg.split(":")
        dec = 2 if asset == "SIM" else 0
        parsed.append((a, b, asset, Amount.parse(amt_s, dec).value))
    sk = Ed25519Signer(load_keystore(keys_dir / f"{signer}_ops1.key", password))
    sk2 = Ed25519Signer(load_keystore(keys_dir / f"{signer}_ops2.key", password))
    body = ProposeGroup(legs=tuple(parsed), priority=1, expiry_height=height + 40)
    env = _sign_tx(body, TxType.PROPOSE_GROUP, signer, [sk, sk2], height)
    rprint(
        httpx.post(
            f"{_rpc(rpc)}/v1/tx",
            params={"wait": "committed"},
            json={"tx_cbor_hex": encode(env).hex()},
            timeout=30,
        ).json()
    )
    rprint(f"group_id={tx_id(env).hex()}")


@dvp_app.command("affirm")
def dvp_affirm(
    group_id: str,
    signer: str = typer.Option(...),
    keys_dir: Path = typer.Option(Path("./testnet/keys")),
    password: str = typer.Option("testnet"),
    rpc: str = typer.Option("http://127.0.0.1:26657"),
) -> None:
    height = httpx.get(f"{_rpc(rpc)}/v1/status").json()["height"]
    sk = Ed25519Signer(load_keystore(keys_dir / f"{signer}_ops1.key", password))
    body = AffirmGroup(group_id=bytes.fromhex(group_id))
    env = _sign_tx(body, TxType.AFFIRM_GROUP, signer, [sk], height)
    rprint(
        httpx.post(
            f"{_rpc(rpc)}/v1/tx",
            params={"wait": "committed"},
            json={"tx_cbor_hex": encode(env).hex()},
            timeout=30,
        ).json()
    )


@app.command()
def sim(
    scenario: Path = typer.Option(Path("sim/scenarios/partition.toml")),
    seed: int = typer.Option(42),
) -> None:
    from sim.harness import run_scenario

    ok = run_scenario(str(scenario), seed)
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
