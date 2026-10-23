"""Tests for bot authorization, command formatting and watchlist editing."""

import pytest

from market_agent.ai.models import ScanReport, TradeAction, TradeOpportunity
from market_agent.bots.auth import parse_allowed_ids
from market_agent.bots.service import HELP_TEXT, BotService, _format_scan
from market_agent.config import AISettings, BotSettings, Settings


def test_parse_allowed_ids():
    assert parse_allowed_ids("") == set()
    assert parse_allowed_ids("123, 456") == {"123", "456"}


def test_bot_authorization():
    settings = Settings(bot=BotSettings(allowed_users="111,222"))
    service = BotService(settings)
    assert service.is_authorized("111")
    assert service.is_authorized("999") is False


def test_bot_open_access_when_no_allowlist():
    settings = Settings(bot=BotSettings(allowed_users=""))
    service = BotService(settings)
    assert service.is_authorized("anyone")


def test_help_lists_discovery_commands():
    for command in (
        "/best",
        "/scan",
        "/movers",
        "/trending",
        "/sector",
        "/insider",
        "/opportunities",
        "/compare",
        "/watchlist",
    ):
        assert command in HELP_TEXT


def make_service() -> BotService:
    return BotService(Settings(ai=AISettings(watchlist="AAPL,MSFT")))


@pytest.mark.asyncio
async def test_watchlist_add_remove_and_clear():
    service = make_service()

    listed = await service.cmd_watchlist("list")
    assert "AAPL" in listed and "MSFT" in listed

    added = await service.cmd_watchlist("add", ["nvda", "AAPL"])
    assert "NVDA" in added
    assert service._watchlist.count("AAPL") == 1, "must not duplicate existing symbols"
    assert service.settings.ai.symbols() == ["AAPL", "MSFT", "NVDA"]

    removed = await service.cmd_watchlist("remove", ["MSFT"])
    assert "MSFT" not in removed.split("\n")[1]

    cleared = await service.cmd_watchlist("clear")
    assert "empty" in cleared


@pytest.mark.asyncio
async def test_watchlist_rejects_unknown_action():
    service = make_service()
    assert "Usage" in await service.cmd_watchlist("frobnicate", ["AAPL"])
    assert service.settings.ai.symbols() == ["AAPL", "MSFT"]


def test_format_scan_includes_levels_and_reasons():
    report = ScanReport(
        scan_type="best_trades",
        universe_size=40,
        scanned=40,
        opportunities=[
            TradeOpportunity(
                symbol="OSCR",
                name="Oscar Health",
                action=TradeAction.BUY,
                score=78.0,
                confidence=0.71,
                price=15.0,
                change_pct=2.4,
                upside_pct=8.5,
                entry_price=15.1,
                stop_loss=13.8,
                take_profit=18.1,
                risk_reward=2.3,
                setup="insider cluster buy",
                reasons=["Bullish forecast at 71% confidence"],
                catalysts=["4 insiders bought $1,500,000"],
                warnings=["Thin volume — slippage risk"],
            )
        ],
        summary="Scanned 40 symbols → 1 opportunity (1 buy).",
    )

    text = _format_scan(report, title="Best Trades")
    assert "OSCR" in text
    assert "BUY" in text
    assert "Entry $15.10" in text and "Stop $13.80" in text and "Target $18.10" in text
    assert "R:R 2.3" in text
    assert "insider cluster buy" in text
    assert "4 insiders bought" in text
    assert "Thin volume" in text


def test_format_scan_with_no_opportunities_shows_summary():
    report = ScanReport(summary="Could not retrieve market data for any of 40 symbols.")
    text = _format_scan(report, title="Best Trades")
    assert "Could not retrieve market data" in text
