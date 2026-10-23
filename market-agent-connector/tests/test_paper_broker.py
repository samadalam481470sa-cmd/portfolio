"""Tests for paper broker."""

import json
from pathlib import Path

import pytest
import httpx
import respx

from market_agent.ai.models import TradeAction, TradeSignal
from market_agent.trader.paper_broker import PaperBroker
from tests.conftest import mock_yahoo_crumb


YAHOO_QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote"


@pytest.fixture
def portfolio_path(tmp_path):
    return str(tmp_path / "test_portfolio.json")


@pytest.mark.asyncio
@respx.mock
async def test_paper_buy_and_sell(portfolio_path):
    mock_yahoo_crumb()
    respx.get(YAHOO_QUOTE).mock(
        return_value=httpx.Response(200, json={
            "quoteResponse": {"result": [{
                "symbol": "AAPL",
                "regularMarketPrice": 150.0,
                "regularMarketPreviousClose": 148.0,
            }]}
        })
    )

    broker = PaperBroker(portfolio_path=portfolio_path, starting_cash=10000)
    try:
        buy_signal = TradeSignal(
            symbol="AAPL", action=TradeAction.BUY, confidence=0.8,
            quantity=10, limit_price=150.0, reasoning="test buy",
        )
        buy_result = await broker.execute(buy_signal)
        assert buy_result.executed
        assert buy_result.order_id

        portfolio = await broker.get_portfolio()
        assert portfolio["positions"]["AAPL"]["quantity"] == 10
        assert portfolio["cash"] == 10000 - 1500

        sell_signal = TradeSignal(
            symbol="AAPL", action=TradeAction.SELL, confidence=0.8,
            quantity=5, limit_price=155.0, reasoning="test sell",
        )
        sell_result = await broker.execute(sell_signal)
        assert sell_result.executed
        assert portfolio_path and Path(portfolio_path).exists()
    finally:
        await broker.close()


@pytest.mark.asyncio
@respx.mock
async def test_paper_insufficient_cash(portfolio_path):
    mock_yahoo_crumb()
    respx.get(YAHOO_QUOTE).mock(
        return_value=httpx.Response(200, json={
            "quoteResponse": {"result": [{
                "symbol": "AMZN",
                "regularMarketPrice": 5000.0,
                "regularMarketPreviousClose": 4900.0,
            }]}
        })
    )

    broker = PaperBroker(portfolio_path=portfolio_path, starting_cash=100.0)
    try:
        signal = TradeSignal(
            symbol="AMZN", action=TradeAction.BUY, confidence=0.9,
            quantity=10, limit_price=5000.0, reasoning="too expensive",
        )
        result = await broker.execute(signal)
        assert not result.executed
    finally:
        await broker.close()
