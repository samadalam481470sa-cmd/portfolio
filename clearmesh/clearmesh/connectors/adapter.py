"""Adapter manifest for wallet / portfolio / brokerage *sandbox* clients."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ConnectorManifest:
    name: str
    chain_id: str
    synthetic: bool
    rest_base: str
    websocket: str
    openapi: str
    disclaimer: str


def build_manifest(rpc_base: str = "http://127.0.0.1:26657") -> dict:
    m = ConnectorManifest(
        name="clearmesh-sim",
        chain_id="clearmesh-sim-1",
        synthetic=True,
        rest_base=f"{rpc_base}/v1",
        websocket=f"{rpc_base.replace('http', 'ws')}/v1/events",
        openapi=f"{rpc_base}/docs",
        disclaimer=(
            "Educational simulation only. No real money, no custody, "
            "no live Robinhood/brokerage/payment-rail connectivity. "
            "Apps may use this OpenAPI surface as a drop-in sandbox backend."
        ),
    )
    return asdict(m)
