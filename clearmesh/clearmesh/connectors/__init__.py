"""External-app connector surface (synthetic testnet only).

Clearmesh intentionally does **not** connect to live brokerage rails,
Robinhood production APIs, or any real-money payment system. Clients
integrate via the OpenAPI REST/WebSocket surface under `/v1`, the same
way a portfolio or regtech sandbox would attach to a permissioned ledger.
"""

from clearmesh.connectors.adapter import ConnectorManifest, build_manifest

__all__ = ["ConnectorManifest", "build_manifest"]
