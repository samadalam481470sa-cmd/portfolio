"""Integration tests against public APIs (no credentials required)."""

import pytest
import respx
import httpx

from market_agent.connectors.kalshi import KalshiConnector
from market_agent.connectors.polymarket import PolymarketConnector
from market_agent.connectors.robinhood import RobinhoodConnector


@pytest.mark.asyncio
async def test_polymarket_health():
    connector = PolymarketConnector()
    try:
        health = await connector.health()
        assert health["platform"] == "polymarket"
        assert health["status"] == "ok"
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_kalshi_health():
    connector = KalshiConnector()
    try:
        health = await connector.health()
        assert health["platform"] == "kalshi"
        assert health["status"] == "ok"
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_robinhood_health_not_configured():
    connector = RobinhoodConnector()
    try:
        health = await connector.health()
        assert health["platform"] == "robinhood"
        assert health["status"] == "not_configured"
    finally:
        await connector.close()


@pytest.mark.asyncio
@respx.mock
async def test_kalshi_list_markets_mock():
    respx.get("https://external-api.demo.kalshi.co/trade-api/v2/markets").mock(
        return_value=httpx.Response(200, json={"markets": [{"ticker": "TEST-1"}]})
    )
    connector = KalshiConnector()
    try:
        result = await connector.list_markets(limit=5)
        assert "markets" in result
        assert result["markets"][0]["ticker"] == "TEST-1"
    finally:
        await connector.close()


@pytest.mark.asyncio
@respx.mock
async def test_polymarket_search_mock():
    respx.get("https://gamma-api.polymarket.com/public-search").mock(
        return_value=httpx.Response(200, json={"events": [], "markets": []})
    )
    connector = PolymarketConnector()
    try:
        result = await connector.search_markets("election")
        assert "events" in result or "markets" in result
    finally:
        await connector.close()
