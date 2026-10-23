"""Tests for position sizer."""

from market_agent.growth.position_sizer import PositionSizer


def test_size_stock_order():
    sizer = PositionSizer(risk_per_trade_pct=0.05, max_position_pct=0.20, min_trade_usd=10)
    shares = sizer.size_stock_order(available_capital=1000, price=100, confidence=0.8)
    assert shares >= 1
    assert shares * 100 <= 200  # max 20% position


def test_size_contract_order():
    sizer = PositionSizer(risk_per_trade_pct=0.03, min_trade_usd=10)
    contracts = sizer.size_contract_order(available_capital=500, contract_price=0.45, confidence=0.7)
    assert contracts >= 1


def test_platform_budget():
    sizer = PositionSizer()
    assert sizer.platform_budget(1000, 0.5) == 500.0
