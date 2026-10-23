"""Robinhood connector — Partner OAuth Brokerage API (requires approved partner access).

Robinhood does not offer a public open API for retail users. This connector
implements the official Partner OAuth 2.0 flow for approved integrations.
Apply at: https://go.robinhood.com/partner
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from market_agent.config import RobinhoodSettings
from market_agent.connectors.base import BaseConnector

# Official partner API base (sandbox vs production)
SANDBOX_URL = "https://sandbox.robinhood.com"
PRODUCTION_URL = "https://api.robinhood.com"


class RobinhoodConnector(BaseConnector):
    name = "robinhood"

    def __init__(self, settings: RobinhoodSettings | None = None) -> None:
        self.settings = settings or RobinhoodSettings()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def base_url(self) -> str:
        return SANDBOX_URL if self.settings.use_sandbox else PRODUCTION_URL

    async def health(self) -> dict[str, Any]:
        return {
            "platform": self.name,
            "status": "configured" if self.settings.client_id else "not_configured",
            "authenticated": self.settings.is_authenticated,
            "note": (
                "Robinhood requires approved Partner API access. "
                "No public retail API is available. Apply at https://go.robinhood.com/partner"
            ),
            "environment": "sandbox" if self.settings.use_sandbox else "production",
        }

    def get_authorization_url(self, state: str = "market-agent") -> str:
        """Build OAuth authorization URL for user consent."""
        if not self.settings.client_id:
            raise ValueError(
                "Robinhood OAuth requires ROBINHOOD_CLIENT_ID. "
                "Apply for partner access at https://go.robinhood.com/partner"
            )
        params = {
            "client_id": self.settings.client_id,
            "response_type": "code",
            "redirect_uri": self.settings.redirect_uri,
            "scope": "read write",
            "state": state,
        }
        return f"{self.base_url}/oauth2/authorize/?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access/refresh tokens."""
        if not self.settings.client_id or not self.settings.client_secret:
            raise ValueError("ROBINHOOD_CLIENT_ID and ROBINHOOD_CLIENT_SECRET required")
        resp = await self._client.post(
            f"{self.base_url}/oauth2/token/",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "redirect_uri": self.settings.redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def refresh_access_token(self) -> dict[str, Any]:
        if not self.settings.refresh_token:
            raise ValueError("ROBINHOOD_REFRESH_TOKEN required to refresh")
        resp = await self._client.post(
            f"{self.base_url}/oauth2/token/",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.settings.refresh_token,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def _auth_headers(self) -> dict[str, str]:
        if not self.settings.is_authenticated:
            raise ValueError(
                "Robinhood authenticated endpoints require ROBINHOOD_ACCESS_TOKEN. "
                "Complete OAuth flow via get_authorization_url() and exchange_code()."
            )
        return {"Authorization": f"Bearer {self.settings.access_token}"}

    async def _request(self, method: str, path: str) -> dict[str, Any]:
        resp = await self._client.request(
            method,
            f"{self.base_url}{path}",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def get_account(self) -> dict[str, Any]:
        return await self._request("GET", "/accounts/")

    async def get_portfolio(self) -> dict[str, Any]:
        return await self._request("GET", "/portfolios/")

    async def get_positions(self) -> dict[str, Any]:
        return await self._request("GET", "/positions/")

    async def get_orders(self) -> dict[str, Any]:
        return await self._request("GET", "/orders/")

    async def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        symbol_param = ",".join(symbols)
        return await self._request("GET", f"/quotes/?symbols={symbol_param}")

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "market",
        limit_price: float | None = None,
        time_in_force: str = "gfd",
    ) -> dict[str, Any]:
        """Place a stock order via Robinhood Partner API."""
        body: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.lower(),
            "quantity": quantity,
            "type": order_type.lower(),
            "time_in_force": time_in_force,
        }
        if order_type.lower() == "limit" and limit_price is not None:
            body["price"] = str(limit_price)

        resp = await self._client.post(
            f"{self.base_url}/orders/",
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()
