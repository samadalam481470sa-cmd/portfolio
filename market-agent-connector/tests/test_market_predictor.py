"""Tests for market predictor."""

import pytest

from market_agent.ai.market_predictor import MarketPredictor
from market_agent.ai.models import AssetType, MarketSnapshot, NewsItem, ResearchBundle, TradeAction


@pytest.mark.asyncio
async def test_predict_bullish_oversold():
    predictor = MarketPredictor()
    research = ResearchBundle(
        symbol="AAPL",
        asset_type=AssetType.STOCK,
        market=MarketSnapshot(symbol="AAPL", price=150.0, change_pct=-2.5),
        technical_signals={
            "rsi_14": 28,
            "trend": "strong_bullish",
            "current_price": 150.0,
            "sma_20": 155.0,
            "sma_50": 148.0,
        },
        news=[NewsItem(title="Apple beats earnings with record growth", source="Reuters")],
    )
    pred = await predictor.predict(research)
    assert pred.direction == "bullish"
    assert pred.recommended_action == TradeAction.BUY
    assert pred.confidence >= 0.5
    assert pred.price_target_1d is not None
    assert pred.buy_zone is not None
    assert pred.sell_zone is not None


@pytest.mark.asyncio
async def test_predict_bearish_overbought():
    predictor = MarketPredictor()
    research = ResearchBundle(
        symbol="NVDA",
        market=MarketSnapshot(symbol="NVDA", price=900.0, change_pct=5.0),
        technical_signals={
            "rsi_14": 78,
            "trend": "strong_bearish",
            "current_price": 900.0,
            "sma_20": 850.0,
        },
        news=[NewsItem(title="NVIDIA faces warning on weak demand", source="Bloomberg")],
    )
    pred = await predictor.predict(research)
    assert pred.direction == "bearish"
    assert pred.recommended_action == TradeAction.SELL


@pytest.mark.asyncio
async def test_support_resistance_use_nearest_levels_not_52_week_extremes():
    predictor = MarketPredictor()
    research = ResearchBundle(
        symbol="MSFT",
        market=MarketSnapshot(
            symbol="MSFT",
            price=480.0,
            change_pct=0.5,
            fifty_two_week_low=344.0,
            fifty_two_week_high=520.0,
        ),
        technical_signals={
            "rsi_14": 55,
            "trend": "bullish",
            "current_price": 480.0,
            "sma_20": 470.0,
            "sma_50": 460.0,
            "fifty_two_week_low": 344.0,
            "fifty_two_week_high": 520.0,
        },
    )
    pred = await predictor.predict(research)

    # Levels must bracket spot closely enough that an order could realistically fill
    assert 400.0 < pred.support < 480.0
    assert 480.0 < pred.resistance < 540.0
    assert pred.buy_zone > 400.0
    assert pred.support < pred.resistance


@pytest.mark.asyncio
async def test_predict_neutral():
    predictor = MarketPredictor()
    research = ResearchBundle(
        symbol="MSFT",
        market=MarketSnapshot(symbol="MSFT", price=400.0, change_pct=0.2),
        technical_signals={"rsi_14": 50, "trend": "neutral", "current_price": 400.0, "sma_20": 399.0},
    )
    pred = await predictor.predict(research)
    assert pred.direction in ("neutral", "bullish", "bearish")
    assert pred.current_price == 400.0
