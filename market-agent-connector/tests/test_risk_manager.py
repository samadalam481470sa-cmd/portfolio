"""Tests for risk manager."""

from market_agent.ai.models import TradeAction, TradeSignal
from market_agent.ai.risk_manager import RiskManager


def test_rejects_low_confidence():
    risk = RiskManager(min_confidence=0.7)
    signal = TradeSignal(
        symbol="AAPL", action=TradeAction.BUY, confidence=0.5,
        quantity=10, reasoning="test",
    )
    valid, msg = risk.validate_signal(signal, current_price=150.0)
    assert not valid
    assert "confidence" in msg.lower()


def test_rejects_oversized_trade():
    risk = RiskManager(max_single_trade_usd=100)
    signal = TradeSignal(
        symbol="AAPL", action=TradeAction.BUY, confidence=0.8,
        quantity=10, reasoning="test",
    )
    valid, msg = risk.validate_signal(signal, current_price=150.0)
    assert not valid
    assert "exceeds" in msg.lower()


def test_approves_valid_signal():
    risk = RiskManager(max_single_trade_usd=500, min_confidence=0.6)
    signal = TradeSignal(
        symbol="AAPL", action=TradeAction.BUY, confidence=0.8,
        quantity=2, reasoning="test",
    )
    valid, msg = risk.validate_signal(signal, current_price=150.0)
    assert valid


def test_dry_run_blocks_execution():
    risk = RiskManager(dry_run=True, require_confirmation=True)
    signal = TradeSignal(
        symbol="AAPL", action=TradeAction.BUY, confidence=0.9,
        quantity=5, reasoning="test",
    )
    assert not risk.should_execute(signal, force=False)
    assert risk.should_execute(signal, force=True)


def test_caps_quantity():
    risk = RiskManager(max_single_trade_usd=500)
    capped = risk.cap_quantity(100, price=200.0)
    assert capped == 2
