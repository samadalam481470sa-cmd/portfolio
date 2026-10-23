"""Kalshi connector — official REST API with RSA-PSS authentication."""

from __future__ import annotations

from typing import Any

import httpx

from market_agent.auth.kalshi_auth import sign_request
from market_agent.config import KalshiSettings, read_private_key_pem
from market_agent.connectors.base import BaseConnector

API_PREFIX = "/trade-api/v2"


class KalshiConnector(BaseConnector):
    name = "kalshi"

    def __init__(self, settings: KalshiSettings | None = None) -> None:
        self.settings = settings or KalshiSettings()
        self._client = httpx.AsyncClient(timeout=30.0)
        self._private_key_pem: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    def _get_private_key(self) -> str:
        if self._private_key_pem is None:
            self._private_key_pem = read_private_key_pem(self.settings)
        return self._private_key_pem

    async def health(self) -> dict[str, Any]:
        try:
            resp = await self._client.get(f"{self.settings.base_url}{API_PREFIX}/exchange/status")
            resp.raise_for_status()
            return {
                "platform": self.name,
                "status": "ok",
                "authenticated": self.settings.is_authenticated,
                "environment": "demo" if self.settings.use_demo else "production",
            }
        except Exception as exc:
            return {"platform": self.name, "status": "error", "error": str(exc)}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.settings.base_url}{path}"
        headers: dict[str, str] = {}

        if auth:
            if not self.settings.is_authenticated:
                raise ValueError(
                    "Kalshi authenticated endpoints require KALSHI_API_KEY_ID "
                    "and KALSHI_PRIVATE_KEY_PATH (or KALSHI_PRIVATE_KEY_PEM)."
                )
            sign_headers = sign_request(self._get_private_key(), method, path)
            headers.update(sign_headers)
            headers["KALSHI-ACCESS-KEY"] = self.settings.api_key_id

        resp = await self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Public: market data ──────────────────────────────────────────────────

    async def get_exchange_status(self) -> dict[str, Any]:
        return await self._request("GET", f"{API_PREFIX}/exchange/status")

    async def list_events(
        self,
        limit: int = 20,
        status: str | None = None,
        series_ticker: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if series_ticker:
            params["series_ticker"] = series_ticker
        return await self._request("GET", f"{API_PREFIX}/events", params=params)

    async def get_event(self, event_ticker: str) -> dict[str, Any]:
        return await self._request("GET", f"{API_PREFIX}/events/{event_ticker}")

    async def list_markets(
        self,
        limit: int = 20,
        status: str = "open",
        event_ticker: str | None = None,
        series_ticker: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "status": status}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        return await self._request("GET", f"{API_PREFIX}/markets", params=params)

    async def get_market(self, ticker: str) -> dict[str, Any]:
        return await self._request("GET", f"{API_PREFIX}/markets/{ticker}")

    async def get_orderbook(self, ticker: str, depth: int = 10) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"{API_PREFIX}/markets/{ticker}/orderbook",
            params={"depth": depth},
        )

    async def get_trades(self, ticker: str | None = None, limit: int = 20) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return await self._request("GET", f"{API_PREFIX}/markets/trades", params=params)

    # ── Authenticated: portfolio & trading ─────────────────────────────────────

    async def get_balance(self) -> dict[str, Any]:
        return await self._request("GET", f"{API_PREFIX}/portfolio/balance", auth=True)

    async def get_positions(
        self,
        ticker: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return await self._request("GET", f"{API_PREFIX}/portfolio/positions", params=params, auth=True)

    async def get_orders(self, status: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        return await self._request("GET", f"{API_PREFIX}/portfolio/orders", params=params, auth=True)

    async def create_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        yes_price: int | None = None,
        no_price: int | None = None,
        order_type: str = "limit",
    ) -> dict[str, Any]:
        """Place an order on Kalshi.

        Args:
            ticker: Market ticker (e.g. KXHIGHNY-24JAN01-T60)
            side: 'yes' or 'no'
            action: 'buy' or 'sell'
            count: Number of contracts
            yes_price: Price in cents (1-99) for yes side limit orders
            no_price: Price in cents (1-99) for no side limit orders
            order_type: 'limit' or 'market'
        """
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": order_type,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        return await self._request("POST", f"{API_PREFIX}/portfolio/orders", json_body=body, auth=True)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"{API_PREFIX}/portfolio/orders/{order_id}",
            auth=True,
        )
