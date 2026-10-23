"""Polymarket connector — Gamma (discovery), Data (positions), CLOB (trading)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from market_agent.auth.polymarket_auth import build_clob_headers
from market_agent.config import PolymarketSettings
from market_agent.connectors.base import BaseConnector

GAMMA_URL = "https://gamma-api.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"


class PolymarketConnector(BaseConnector):
    name = "polymarket"

    def __init__(self, settings: PolymarketSettings | None = None) -> None:
        self.settings = settings or PolymarketSettings()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            resp = await self._client.get(f"{GAMMA_URL}/events", params={"limit": 1})
            resp.raise_for_status()
            return {
                "platform": self.name,
                "status": "ok",
                "authenticated": self.settings.is_authenticated,
                "apis": ["gamma", "data", "clob"],
            }
        except Exception as exc:
            return {"platform": self.name, "status": "error", "error": str(exc)}

    # ── Public: Gamma API (market discovery) ─────────────────────────────────

    async def search_markets(self, query: str, limit: int = 10) -> dict[str, Any]:
        resp = await self._client.get(
            f"{GAMMA_URL}/public-search",
            params={"q": query, "limit_per_type": limit},
        )
        resp.raise_for_status()
        return resp.json()

    async def list_events(
        self,
        limit: int = 20,
        active: bool = True,
        tag: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "active": str(active).lower()}
        if tag:
            params["tag_slug"] = tag
        resp = await self._client.get(f"{GAMMA_URL}/events", params=params)
        resp.raise_for_status()
        return resp.json()

    async def list_markets(
        self,
        limit: int = 50,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": limit,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if tag:
            params["tag_slug"] = tag
        resp = await self._client.get(f"{GAMMA_URL}/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("data", [])

    async def get_event(self, slug: str) -> dict[str, Any]:
        resp = await self._client.get(f"{GAMMA_URL}/events/slug/{slug}")
        resp.raise_for_status()
        return resp.json()

    async def get_market(self, condition_id: str) -> dict[str, Any]:
        resp = await self._client.get(f"{GAMMA_URL}/markets/{condition_id}")
        resp.raise_for_status()
        return resp.json()

    # ── Public: CLOB API (orderbook & prices) ────────────────────────────────

    async def get_orderbook(self, token_id: str) -> dict[str, Any]:
        resp = await self._client.get(f"{CLOB_URL}/book", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    async def get_midpoint(self, token_id: str) -> dict[str, Any]:
        resp = await self._client.get(f"{CLOB_URL}/midpoint", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    async def get_price(self, token_id: str, side: str = "buy") -> dict[str, Any]:
        resp = await self._client.get(
            f"{CLOB_URL}/price",
            params={"token_id": token_id, "side": side},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Public: Data API (user positions by address) ─────────────────────────

    async def get_positions(self, user_address: str | None = None) -> list[dict[str, Any]]:
        address = user_address or self.settings.wallet_address
        if not address:
            raise ValueError("Wallet address required (set POLYMARKET_WALLET_ADDRESS or pass user_address)")
        resp = await self._client.get(f"{DATA_URL}/positions", params={"user": address})
        resp.raise_for_status()
        return resp.json()

    async def get_user_trades(self, user_address: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        address = user_address or self.settings.wallet_address
        if not address:
            raise ValueError("Wallet address required")
        resp = await self._client.get(
            f"{DATA_URL}/trades",
            params={"user": address, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Authenticated: CLOB trading ──────────────────────────────────────────

    def _require_auth(self) -> None:
        if not self.settings.is_authenticated:
            raise ValueError(
                "Polymarket trading requires CLOB credentials. "
                "Set POLYMARKET_CLOB_API_KEY, POLYMARKET_CLOB_SECRET, "
                "POLYMARKET_CLOB_PASSPHRASE, and POLYMARKET_WALLET_ADDRESS."
            )

    async def _clob_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_auth()
        body_str = json.dumps(body) if body else ""
        headers = build_clob_headers(
            self.settings.clob_api_key,
            self.settings.clob_secret,
            self.settings.clob_passphrase,
            self.settings.wallet_address,
            method,
            path,
            body_str,
        )
        headers["Content-Type"] = "application/json"
        resp = await self._client.request(
            method,
            f"{CLOB_URL}{path}",
            headers=headers,
            content=body_str if body else None,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_open_orders(self) -> list[dict[str, Any]]:
        return await self._clob_request("GET", "/data/orders")

    async def place_limit_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str,
    ) -> dict[str, Any]:
        body = {
            "tokenID": token_id,
            "price": price,
            "size": size,
            "side": side.upper(),
            "type": "GTC",
        }
        return await self._clob_request("POST", "/order", body)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return await self._clob_request("DELETE", f"/order/{order_id}")

    async def cancel_all_orders(self) -> dict[str, Any]:
        return await self._clob_request("DELETE", "/cancel-all")
