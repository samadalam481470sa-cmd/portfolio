"""Shared Yahoo Finance HTTP session.

Yahoo's quote API requires a cookie + crumb pair obtained from a browser-like
handshake, and it rate-limits aggressively from datacenter IPs. This session
handles both concerns in one place: it lazily acquires a crumb, retries with
backoff on 429, and returns ``None`` instead of raising so callers can fall
back to another endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

QUERY_HOST = "https://query1.finance.yahoo.com"
CHART_URL = QUERY_HOST + "/v8/finance/chart/{symbol}"
QUOTE_URL = QUERY_HOST + "/v7/finance/quote"
TRENDING_URL = QUERY_HOST + "/v1/finance/trending/US"
SCREENER_URL = QUERY_HOST + "/v1/finance/screener/predefined/saved"
CRUMB_URL = QUERY_HOST + "/v1/test/getcrumb"
COOKIE_URL = "https://fc.yahoo.com"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0


class YahooSession:
    """HTTP session for Yahoo Finance endpoints with crumb auth and backoff."""

    def __init__(self, timeout: float = 25.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout, headers=BROWSER_HEADERS, follow_redirects=True
        )
        self._crumb: str | None = None
        self._crumb_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        needs_crumb: bool = False,
    ) -> dict[str, Any] | None:
        """Fetch JSON, returning None if the endpoint stays unavailable."""
        params = dict(params or {})
        refreshed_crumb = False

        for attempt in range(MAX_RETRIES):
            if needs_crumb:
                crumb = await self._get_crumb()
                if crumb:
                    params["crumb"] = crumb

            try:
                resp = await self._client.get(url, params=params)
            except httpx.HTTPError:
                await self._backoff(attempt)
                continue

            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    return None

            # A stale crumb reads as an auth failure; get a fresh one once.
            if resp.status_code in (401, 403) and needs_crumb and not refreshed_crumb:
                refreshed_crumb = True
                self._crumb = None
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                await self._backoff(attempt)
                continue

            return None

        return None

    async def _get_crumb(self) -> str | None:
        if self._crumb:
            return self._crumb
        async with self._crumb_lock:
            if self._crumb:
                return self._crumb
            try:
                await self._client.get(COOKIE_URL)
                resp = await self._client.get(CRUMB_URL)
                if resp.status_code == 200:
                    crumb = resp.text.strip()
                    # Error pages come back as prose rather than an opaque token
                    if crumb and len(crumb) < 32 and " " not in crumb:
                        self._crumb = crumb
            except httpx.HTTPError:
                pass
        return self._crumb

    @staticmethod
    async def _backoff(attempt: int) -> None:
        await asyncio.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
