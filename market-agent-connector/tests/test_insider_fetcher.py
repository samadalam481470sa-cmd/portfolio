"""Tests for OpenInsider insider trade fetcher."""

import pytest
import httpx
import respx

from market_agent.intelligence.insider_fetcher import (
    InsiderFetcher,
    _parse_row,
    _parse_row_any,
    _summarize,
)
from market_agent.ai.models import InsiderTrade

SAMPLE_HTML = """
<html><body>
<table class="tinytable">
<tr><td>X</td><td>Filing Date</td><td>Trade Date</td><td>Ticker</td></tr>
<tr>
  <td></td>
  <td>2026-08-13 18:30:20</td>
  <td>2026-08-11</td>
  <td>AAPL</td>
  <td>Cook Timothy D</td>
  <td>CEO</td>
  <td>P - Purchase</td>
  <td>$200.00</td>
  <td>+10,000</td>
  <td>3,280,418</td>
  <td>+0%</td>
  <td>+$2,000,000</td>
</tr>
<tr>
  <td>D</td>
  <td>2026-05-08 18:30:09</td>
  <td>2026-05-06</td>
  <td>AAPL</td>
  <td>Levinson Arthur D</td>
  <td>Dir</td>
  <td>S - Sale</td>
  <td>$284.76</td>
  <td>-250,000</td>
  <td>3,870,576</td>
  <td>-6%</td>
  <td>-$71,189,722</td>
</tr>
</table>
</body></html>
"""


def test_parse_row_purchase():
    cells = [
        "2026-08-13 18:30:20", "2026-08-11", "AAPL", "Cook Timothy D", "CEO",
        "P - Purchase", "$200.00", "+10,000", "3,280,418", "+0%", "+$2,000,000",
    ]
    trade = _parse_row(cells, "AAPL")
    assert trade is not None
    assert trade.insider_name == "Cook Timothy D"
    assert trade.is_purchase
    assert trade.quantity == 10000
    assert trade.value == 2_000_000


def test_parse_row_sale():
    cells = [
        "2026-05-08 18:30:09", "2026-05-06", "AAPL", "Levinson Arthur D", "Dir",
        "S - Sale", "$284.76", "-250,000", "3,870,576", "-6%", "-$71,189,722",
    ]
    trade = _parse_row(cells, "AAPL")
    assert trade is not None
    assert trade.is_sale
    assert trade.quantity == 250000


def test_summarize_sentiment():
    trades = [
        InsiderTrade(
            symbol="AAPL", insider_name="A", trade_type="P - Purchase",
            trade_date="2026-01-01", value=500_000, quantity=1000, price=500,
        ),
        InsiderTrade(
            symbol="AAPL", insider_name="B", trade_type="S - Sale",
            trade_date="2026-01-02", value=100_000, quantity=500, price=200,
        ),
    ]
    summary = _summarize("AAPL", trades, 90)
    assert summary.net_sentiment == "bullish"
    assert summary.purchases == 1
    assert summary.sales == 1


@pytest.mark.asyncio
@respx.mock
async def test_fetch_openinsider_mock():
    respx.get("http://openinsider.com/screener").mock(
        return_value=httpx.Response(200, text=SAMPLE_HTML)
    )
    fetcher = InsiderFetcher()
    try:
        trades = await fetcher.get_trades("AAPL", limit=10, days=365)
        assert len(trades) >= 1
        assert trades[0].symbol == "AAPL"
    finally:
        await fetcher.close()


# ── Market-wide screening (ticker unknown up front) ─────────────────────────────

CLUSTER_HTML = """
<html><body>
<table class="tinytable">
<tr><td>X</td><td>Filing Date</td><td>Trade Date</td><td>Ticker</td></tr>
<tr>
  <td></td><td>2026-08-13 18:30:20</td><td>2026-08-11</td><td>OSCR</td>
  <td>Alice Founder</td><td>CEO</td><td>P - Purchase</td><td>$14.00</td>
  <td>+50,000</td><td>500,000</td><td>+11%</td><td>+$700,000</td>
</tr>
<tr>
  <td>D</td><td>2026-08-13 17:10:00</td><td>2026-08-11</td><td>OSCR</td>
  <td>Bob Director</td><td>Dir</td><td>P - Purchase</td><td>$14.10</td>
  <td>+20,000</td><td>120,000</td><td>+20%</td><td>+$282,000</td>
</tr>
<tr>
  <td></td><td>2026-08-12 16:05:00</td><td>2026-08-10</td><td>SOLO</td>
  <td>Carol Officer</td><td>CFO</td><td>P - Purchase</td><td>$8.00</td>
  <td>+25,000</td><td>75,000</td><td>+50%</td><td>+$200,000</td>
</tr>
</table>
</body></html>
"""


def test_parse_row_any_locates_ticker_without_hint():
    cells = [
        "2026-08-13 18:30:20", "2026-08-11", "OSCR", "Alice Founder", "CEO",
        "P - Purchase", "$14.00", "+50,000", "500,000", "+11%", "+$700,000",
    ]
    trade = _parse_row_any(cells)
    assert trade is not None
    assert trade.symbol == "OSCR"
    assert trade.insider_name == "Alice Founder"
    assert trade.is_purchase
    assert trade.value == 700_000


def test_parse_row_any_rejects_rows_without_dates():
    assert _parse_row_any(["Filing Date", "Trade Date", "Ticker", "Insider"]) is None
    assert _parse_row_any([]) is None


@pytest.mark.asyncio
@respx.mock
async def test_market_wide_buys_filters_by_value():
    respx.get("http://openinsider.com/screener").mock(
        return_value=httpx.Response(200, text=CLUSTER_HTML)
    )
    fetcher = InsiderFetcher()
    try:
        trades = await fetcher.get_market_wide_buys(days=7, min_value_usd=250_000)
        symbols = [t.symbol for t in trades]
        assert symbols == ["OSCR", "OSCR"]  # SOLO's $200k buy is below the floor
        assert all(t.is_purchase for t in trades)
    finally:
        await fetcher.close()


@pytest.mark.asyncio
@respx.mock
async def test_cluster_buys_groups_by_symbol():
    respx.get("http://openinsider.com/screener").mock(
        return_value=httpx.Response(200, text=CLUSTER_HTML)
    )
    fetcher = InsiderFetcher()
    try:
        clusters = await fetcher.get_cluster_buys(days=14, min_insiders=2)
        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster["symbol"] == "OSCR"
        assert cluster["insider_count"] == 2
        assert cluster["total_value_usd"] == pytest.approx(982_000)
        assert cluster["latest_date"] == "2026-08-11"
    finally:
        await fetcher.close()


@pytest.mark.asyncio
@respx.mock
async def test_market_wide_buys_returns_empty_on_error():
    respx.get("http://openinsider.com/screener").mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    fetcher = InsiderFetcher()
    try:
        assert await fetcher.get_market_wide_buys() == []
        assert await fetcher.get_cluster_buys() == []
    finally:
        await fetcher.close()
