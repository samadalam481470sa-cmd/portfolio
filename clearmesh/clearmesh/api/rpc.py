"""FastAPI REST /v1 + WS /v1/events + /metrics."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from clearmesh.api.events import EventBus
from clearmesh.core.codec import decode, encode
from clearmesh.state.overlay import Overlay
from clearmesh.state.world import WorldView
from clearmesh.types.block import Block, Commit
from clearmesh.types.tx import TxEnvelope

BLOCK_HEIGHT = Gauge("clearmesh_block_height", "Latest committed height")
MEMPOOL_SIZE = Gauge("clearmesh_mempool_size", "Mempool size")
COMPLIANCE_REJ = Counter(
    "clearmesh_compliance_rejections_total", "Compliance rejections", ["reason"]
)
FINALITY = Histogram("clearmesh_time_to_finality_seconds", "Time to finality")


class TxSubmit(BaseModel):
    tx_cbor_hex: str = Field(..., description="Canonical CBOR TxEnvelope hex")


def create_app(node: Any) -> FastAPI:
    app = FastAPI(title="Clearmesh RPC", version="0.1.0")
    bus = EventBus()
    app.state.bus = bus
    app.state.node = node

    if node.sequencer:

        def _on_block(block: Block, commit: Commit, receipts: list[Any]) -> None:
            BLOCK_HEIGHT.set(block.header.height)
            MEMPOOL_SIZE.set(node.sequencer.mempool.size())
            bus.publish(
                {
                    "type": "NewBlock",
                    "height": block.header.height,
                    "tx_count": len(block.txs),
                }
            )
            for r in receipts:
                bus.publish(
                    {
                        "type": "InstructionStatusChanged",
                        "subject": r.subject,
                        "to_status": r.to_status,
                        "height": r.height,
                    },
                    participant=r.subject if r.subject.startswith("BANK") else None,
                )

        node.sequencer.on_block(_on_block)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "clearmesh"}

    @app.get("/metrics")
    def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/status")
    def status() -> dict[str, Any]:
        seq = node.sequencer
        return {
            "height": seq.height if seq else 0,
            "chain_id": node.config.chain_id,
            "solo": node.config.solo,
            "mempool": seq.mempool.size() if seq else 0,
            "demo_evil_rpc": node.config.demo_evil_rpc,
        }

    @app.post("/v1/tx")
    def submit_tx(
        body: TxSubmit, wait: str = Query("checked", pattern="^(none|checked|committed)$")
    ) -> dict[str, Any]:
        seq = node.sequencer
        if not seq:
            raise HTTPException(503, "sequencer down")
        try:
            env = decode(TxEnvelope, bytes.fromhex(body.tx_cbor_hex))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"decode: {exc}") from exc
        tid, admitted, reason = seq.submit_tx(env)
        height = None
        if wait == "committed" and admitted:
            # produce immediately for demo responsiveness
            block, _ = seq.produce_block()
            height = block.header.height
        elif wait == "checked" and admitted:
            pass
        if not admitted and reason.startswith("RR"):
            COMPLIANCE_REJ.labels(reason=reason).inc()
        return {
            "tx_id": tid.hex(),
            "admitted": admitted,
            "reason_code": reason,
            "height": height,
        }

    @app.get("/v1/blocks/latest")
    def latest_block() -> dict[str, Any]:
        seq = node.sequencer
        if not seq or not seq.latest_block():
            raise HTTPException(404, "no blocks")
        block, commit = seq.latest_block()
        return _block_json(block, commit)

    @app.get("/v1/blocks/{height}")
    def get_block(height: int) -> dict[str, Any]:
        store = node.store
        row = store.get_block(height)
        if row is None:
            raise HTTPException(404, "not found")
        block = decode(Block, row[0])
        commit = decode(Commit, row[1])
        return _block_json(block, commit)

    @app.get("/v1/accounts/{pid}")
    def account(pid: str, prove: bool = False) -> dict[str, Any]:
        store = node.store
        world = WorldView(Overlay(store))
        acct = world.get_account(pid)
        if acct is None:
            raise HTTPException(404, "unknown participant")
        balances: dict[str, int] = {}
        for k, v in world.o.scan(f"bal/{pid}/"):
            asset = k.decode().split("/")[-1]
            balances[asset] = decode(int, v)  # type: ignore[arg-type]
        # Evil RPC demo: lie about balance
        if node.config.demo_evil_rpc and "SIM" in balances:
            balances["SIM"] = balances["SIM"] + 1_000_00
        out: dict[str, Any] = {
            "participant": pid,
            "frozen": acct.frozen,
            "debit_caps": dict(acct.debit_caps),
            "balances": balances,
        }
        if prove and node.sequencer and node.sequencer.latest_block():
            block, commit = node.sequencer.latest_block()
            out["header"] = {
                "height": block.header.height,
                "state_root": block.header.state_root.hex(),
                "liabilities_root": block.header.liabilities_root.hex(),
            }
            out["commit_sigs"] = len(commit.sigs)
        return out

    @app.get("/v1/instructions/{uetr}")
    def instruction(uetr: str) -> dict[str, Any]:
        world = WorldView(Overlay(node.store))
        instr = world.get_instruction(uetr)
        if instr is None:
            raise HTTPException(404, "not found")
        return {
            "uetr": instr.uetr,
            "status": instr.status,
            "debtor": instr.debtor,
            "creditor": instr.creditor,
            "asset": instr.asset,
            "amount": instr.amount,
            "method": instr.method,
            "settled_height": instr.settled_height,
            "envelope_commitment": instr.envelope_commitment.hex(),
            "kind": instr.kind,
            "priority": instr.priority,
        }

    @app.get("/v1/queue")
    def queue(debtor: str | None = None) -> dict[str, Any]:
        from clearmesh.settlement import queue as Q

        world = WorldView(Overlay(node.store))
        debtors = [debtor] if debtor else Q.all_debtors(world)
        items = {d: [{"uetr": u, "priority": p, "seq": s} for u, p, s in Q.items(world, d)] for d in debtors}
        return {"queues": items}

    @app.get("/v1/invariants")
    def invariants() -> dict[str, Any]:
        from clearmesh.ledger.journal import check_invariants

        world = WorldView(Overlay(node.store))
        errs = check_invariants(world)
        return {"ok": not errs, "errors": errs}

    @app.get("/v1/policy")
    def policy() -> dict[str, Any]:
        world = WorldView(Overlay(node.store))
        pol = world.get_policy()
        if pol is None:
            raise HTTPException(404, "no policy")
        return {
            "maker_checker_threshold": pol.maker_checker_threshold,
            "netting_interval_blocks": pol.netting_interval_blocks,
            "max_tx_ttl": pol.max_tx_ttl,
        }

    @app.get("/v1/validators")
    def validators() -> dict[str, Any]:
        g = node.genesis
        return {
            "validators": [
                {"id": v.participant_id, "pubkey": v.pubkey_hex, "power": v.power}
                for v in g.validators
            ]
        }

    @app.get("/v1/netting")
    def netting(last: int = 50) -> dict[str, Any]:
        world = WorldView(Overlay(node.store))
        reports = []
        for k, v in world.o.scan("nrep/"):
            from clearmesh.types.records import NettingReport

            rep = decode(NettingReport, v)
            reports.append(
                {
                    "cycle_id": rep.cycle_id.hex(),
                    "height": rep.height,
                    "settled": len(rep.settled),
                    "deferred": len(rep.deferred),
                    "per_asset": [
                        {
                            "asset": a.asset,
                            "gross": a.gross,
                            "liquidity_used": a.liquidity_used,
                            "lsr_bps": a.lsr_bps,
                        }
                        for a in rep.per_asset
                    ],
                }
            )
        reports.sort(key=lambda x: x["height"], reverse=True)
        return {"reports": reports[:last]}

    @app.get("/v1/evidence")
    def evidence() -> dict[str, Any]:
        world = WorldView(Overlay(node.store))
        items = [k.decode() for k, _ in world.o.scan("evid/")]
        return {"evidence": items}

    @app.websocket("/v1/events")
    async def events(ws: WebSocket, participant: str | None = None) -> None:
        await ws.accept()
        q = bus.subscribe(participant)
        try:
            while True:
                ev = await q.get()
                await ws.send_json(ev)
        except WebSocketDisconnect:
            bus.unsubscribe(q, participant)

    # External-app connector surface (synthetic; not a real brokerage rail)
    @app.get("/v1/connectors/manifest")
    def connectors_manifest() -> dict[str, Any]:
        return {
            "name": "clearmesh-connector",
            "synthetic": True,
            "disclaimer": (
                "Educational simulation only. No real money, no custody, "
                "no connection to live brokerage or payment rails."
            ),
            "interfaces": [
                {"type": "rest", "base": "/v1", "openapi": "/docs"},
                {"type": "websocket", "path": "/v1/events"},
                {
                    "type": "webhook_stub",
                    "path": "/v1/connectors/webhook-echo",
                    "note": "Signed webhook delivery is a stretch goal",
                },
            ],
            "compatible_client_patterns": [
                "OpenAPI-generated clients",
                "Portfolio dashboard adapters",
                "Regtech screening sandboxes",
            ],
        }

    @app.post("/v1/connectors/webhook-echo")
    def webhook_echo(payload: dict[str, Any]) -> dict[str, Any]:
        return {"received": True, "echo": payload, "synthetic": True}

    return app


def _block_json(block: Block, commit: Commit) -> dict[str, Any]:
    from clearmesh.types.tx import tx_id

    return {
        "height": block.header.height,
        "round": block.header.round,
        "time_ms": block.header.time_ms,
        "proposer_index": block.header.proposer_index,
        "tx_ids": [tx_id(t).hex() for t in block.txs],
        "state_root": block.header.state_root.hex(),
        "receipts_root": block.header.receipts_root.hex(),
        "liabilities_root": block.header.liabilities_root.hex(),
        "commit_sigs": len(commit.sigs),
        "sanctions_version": block.header.sanctions_version,
    }
