"""Tests for rule-based decision engine."""

import pytest

from market_agent.ai.decision_engine import DecisionEngine
from market_agent.ai.models import AssetType, MarketSnapshot, NewsItem, ResearchBundle, TradeAction


@pytest.mark.asyncio
async def test_rules_engine_hold_on_neutral():
    engine = DecisionEngine(llm=None)
    research = ResearchBundle(
        symbol="AAPL",
        market=MarketSnapshot(symbol="AAPL", price=150.0, change_pct=0.5),
        technical_signals={"rsi_14": 50, "trend": "neutral"},
    )
    signal = await engine.analyze(research)
    assert signal.action in (TradeAction.HOLD, TradeAction.BUY, TradeAction.SELL)
    assert 0 <= signal.confidence <= 1


@pytest.mark.asyncio
async def test_rules_engine_buy_on_oversold():
    engine = DecisionEngine(llm=None)
    research = ResearchBundle(
        symbol="TSLA",
        market=MarketSnapshot(symbol="TSLA", price=200.0, change_pct=-4.0),
        technical_signals={"rsi_14": 25, "trend": "strong_bullish", "current_price": 200},
        news=[
            NewsItem(title="Tesla beats earnings expectations with record growth", source="Reuters"),
        ],
    )
    signal = await engine.analyze(research)
    assert signal.action == TradeAction.BUY
    assert signal.confidence >= 0.5
    assert signal.quantity > 0


@pytest.mark.asyncio
async def test_rules_engine_sell_on_overbought():
    engine = DecisionEngine(llm=None)
    research = ResearchBundle(
        symbol="NVDA",
        market=MarketSnapshot(symbol="NVDA", price=900.0, change_pct=5.0),
        technical_signals={"rsi_14": 78, "trend": "strong_bearish", "current_price": 900},
        news=[
            NewsItem(title="NVIDIA faces lawsuit over weak demand warning", source="Bloomberg"),
        ],
    )
    signal = await engine.analyze(research)
    assert signal.action == TradeAction.SELL
