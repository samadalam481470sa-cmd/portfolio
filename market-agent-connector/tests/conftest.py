"""Shared test helpers."""

from __future__ import annotations

import httpx
import respx

from market_agent.intelligence.yahoo import COOKIE_URL, CRUMB_URL


def mock_yahoo_crumb(crumb: str = "testcrumb") -> None:
    """Register the cookie + crumb handshake the Yahoo quote API requires.

    Call this inside an active ``respx.mock`` context before exercising code
    that fetches quotes, otherwise the handshake fails the mock assertion.
    """
    respx.get(COOKIE_URL).mock(return_value=httpx.Response(200, text=""))
    respx.get(CRUMB_URL).mock(return_value=httpx.Response(200, text=crumb))
