"""Tests for the Yahoo session and market data fetcher fallbacks."""

from __future__ import annotations

import httpx
import pytest
import respx

from market_agent.intelligence import yahoo
from market_agent.intelligence.market_data import (
    MarketDataFetcher,
    _snapshot_from_chart_meta,
)
from market_agent.intelligence.yahoo import (
    CHART_URL,
    QUOTE_URL,
    SCREENER_URL,
    YahooSession,
)
from tests.conftest import mock_yahoo_crumb


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    """Keep retry tests fast."""
    monkeypatch.setattr(yahoo, "BACKOFF_BASE_SECONDS", 0.0)


def chart_response(price: float = 100.0, prev: float = 95.0, symbol: str = "AAPL") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "regularMarketPrice": price,
                            "previousClose": prev,
                            "regularMarketVolume": 1_234_567,
                            "fiftyTwoWeekHigh": 120.0,
                            "fiftyTwoWeekLow": 80.0,
                            "longName": f"{symbol} Inc.",
                            "currency": "USD",
                        },
                        "indicators": {"quote": [{"close": [90.0 + i for i in range(60)]}]},
                    }
                ]
            }
        },
    )


# ── YahooSession ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_session_attaches_crumb_to_quote_requests():
    mock_yahoo_crumb("abc123")
    route = respx.get(QUOTE_URL).mock(
        return_value=httpx.Response(200, json={"quoteResponse": {"result": []}})
    )

    session = YahooSession()
    try:
        await session.get_json(QUOTE_URL, {"symbols": "AAPL"}, needs_crumb=True)
    finally:
        await session.close()

    assert route.called
    assert route.calls[0].request.url.params["crumb"] == "abc123"


@pytest.mark.asyncio
@respx.mock
async def test_session_retries_on_rate_limit_then_succeeds():
    route = respx.get(SCREENER_URL).mock(
        side_effect=[
            httpx.Response(429, text="Too Many Requests"),
            httpx.Response(200, json={"finance": {"result": [{"quotes": []}]}}),
        ]
    )

    session = YahooSession()
    try:
        data = await session.get_json(SCREENER_URL, {"scrIds": "day_gainers"})
    finally:
        await session.close()

    assert data is not None
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_session_returns_none_when_rate_limit_persists():
    respx.get(SCREENER_URL).mock(return_value=httpx.Response(429, text="nope"))

    session = YahooSession()
    try:
        assert await session.get_json(SCREENER_URL) is None
    finally:
        await session.close()


@pytest.mark.asyncio
@respx.mock
async def test_session_refreshes_crumb_once_on_401():
    respx.get(yahoo.COOKIE_URL).mock(return_value=httpx.Response(200, text=""))
    crumb_route = respx.get(yahoo.CRUMB_URL).mock(
        side_effect=[httpx.Response(200, text="stale"), httpx.Response(200, text="fresh")]
    )
    quote_route = respx.get(QUOTE_URL).mock(
        side_effect=[
            httpx.Response(401, text="Unauthorized"),
            httpx.Response(200, json={"quoteResponse": {"result": [{"symbol": "AAPL"}]}}),
        ]
    )

    session = YahooSession()
    try:
        data = await session.get_json(QUOTE_URL, {"symbols": "AAPL"}, needs_crumb=True)
    finally:
        await session.close()

    assert data is not None
    assert crumb_route.call_count == 2
    assert quote_route.calls[1].request.url.params["crumb"] == "fresh"


@pytest.mark.asyncio
@respx.mock
async def test_session_rejects_error_page_as_crumb():
    respx.get(yahoo.COOKIE_URL).mock(return_value=httpx.Response(200, text=""))
    respx.get(yahoo.CRUMB_URL).mock(
        return_value=httpx.Response(200, text="Too Many Requests\r\n")
    )
    route = respx.get(QUOTE_URL).mock(
        return_value=httpx.Response(200, json={"quoteResponse": {"result": []}})
    )

    session = YahooSession()
    try:
        await session.get_json(QUOTE_URL, {"symbols": "AAPL"}, needs_crumb=True)
    finally:
        await session.close()

    assert "crumb" not in route.calls[0].request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_session_returns_none_on_client_error():
    respx.get(SCREENER_URL).mock(return_value=httpx.Response(404, text="missing"))
    session = YahooSession()
    try:
        assert await session.get_json(SCREENER_URL) is None
    finally:
        await session.close()


# ── MarketDataFetcher ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_get_quote_uses_quote_api_when_available():
    mock_yahoo_crumb()
    respx.get(QUOTE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "quoteResponse": {
                    "result": [
                        {
                            "symbol": "AAPL",
                            "regularMarketPrice": 200.0,
                            "regularMarketPreviousClose": 190.0,
                            "marketCap": 3_000_000_000_000,
                            "trailingPE": 30.5,
                            "shortName": "Apple Inc.",
                        }
                    ]
                }
            },
        )
    )

    fetcher = MarketDataFetcher()
    try:
        snap = await fetcher.get_quote("aapl")
    finally:
        await fetcher.close()

    assert snap.symbol == "AAPL"
    assert snap.price == 200.0
    assert snap.change_pct == pytest.approx(5.26, abs=0.01)
    assert snap.pe_ratio == 30.5
    assert snap.extra["source"] == "yahoo_quote"


@pytest.mark.asyncio
@respx.mock
async def test_get_quote_falls_back_to_chart_when_quotes_unauthorized():
    mock_yahoo_crumb()
    respx.get(QUOTE_URL).mock(return_value=httpx.Response(401, text="Unauthorized"))
    respx.get(url__regex=r".*/v8/finance/chart/AAPL.*").mock(
        return_value=chart_response(price=200.0, prev=190.0)
    )

    fetcher = MarketDataFetcher()
    try:
        snap = await fetcher.get_quote("AAPL")
    finally:
        await fetcher.close()

    assert snap.price == 200.0
    assert snap.change_pct == pytest.approx(5.26, abs=0.01)
    assert snap.volume == 1_234_567
    assert snap.extra["source"] == "yahoo_chart"
    # The chart endpoint carries no fundamentals
    assert snap.market_cap is None


@pytest.mark.asyncio
@respx.mock
async def test_get_quote_raises_when_both_endpoints_fail():
    mock_yahoo_crumb()
    respx.get(QUOTE_URL).mock(return_value=httpx.Response(401))
    respx.get(url__regex=r".*/v8/finance/chart/.*").mock(return_value=httpx.Response(404))

    fetcher = MarketDataFetcher()
    try:
        with pytest.raises(ValueError, match="No market data"):
            await fetcher.get_quote("NOPE")
    finally:
        await fetcher.close()


@pytest.mark.asyncio
@respx.mock
async def test_get_quotes_fills_missing_symbols_from_chart():
    mock_yahoo_crumb()
    respx.get(QUOTE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "quoteResponse": {
                    "result": [
                        {
                            "symbol": "AAPL",
                            "regularMarketPrice": 200.0,
                            "regularMarketPreviousClose": 190.0,
                        }
                    ]
                }
            },
        )
    )
    respx.get(url__regex=r".*/v8/finance/chart/MSFT.*").mock(
        return_value=chart_response(price=400.0, prev=395.0, symbol="MSFT")
    )

    fetcher = MarketDataFetcher()
    try:
        snaps = await fetcher.get_quotes(["AAPL", "MSFT"])
    finally:
        await fetcher.close()

    by_symbol = {s.symbol: s for s in snaps}
    assert by_symbol["AAPL"].extra["source"] == "yahoo_quote"
    assert by_symbol["MSFT"].extra["source"] == "yahoo_chart"
    assert by_symbol["MSFT"].price == 400.0


@pytest.mark.asyncio
async def test_get_quotes_empty_input_makes_no_requests():
    fetcher = MarketDataFetcher()
    try:
        assert await fetcher.get_quotes([]) == []
    finally:
        await fetcher.close()


@pytest.mark.asyncio
@respx.mock
async def test_get_technicals_returns_empty_when_chart_blocked():
    respx.get(url__regex=r".*/v8/finance/chart/.*").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    fetcher = MarketDataFetcher()
    try:
        assert await fetcher.get_technicals("AAPL") == {}
    finally:
        await fetcher.close()


@pytest.mark.asyncio
@respx.mock
async def test_get_technicals_computes_indicators():
    respx.get(url__regex=r".*/v8/finance/chart/AAPL.*").mock(
        return_value=chart_response()
    )
    fetcher = MarketDataFetcher()
    try:
        tech = await fetcher.get_technicals("AAPL")
    finally:
        await fetcher.close()

    assert tech["sma_20"] and tech["sma_50"]
    assert 0 <= tech["rsi_14"] <= 100
    assert tech["trend"] in ("bullish", "bearish", "strong_bullish", "strong_bearish")


def test_snapshot_from_chart_meta_requires_price():
    assert _snapshot_from_chart_meta({}, "AAPL") is None
    snap = _snapshot_from_chart_meta(
        {"regularMarketPrice": 50.0, "chartPreviousClose": 40.0}, "aapl"
    )
    assert snap is not None
    assert snap.symbol == "AAPL"
    assert snap.change_pct == pytest.approx(25.0)


def test_chart_url_is_unauthenticated_endpoint():
    assert "/v8/finance/chart/" in CHART_URL
