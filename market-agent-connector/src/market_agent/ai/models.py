"""Data models for AI trading decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TradeAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class AssetType(str, Enum):
    STOCK = "stock"
    PREDICTION = "prediction"
    CRYPTO_MARKET = "crypto_market"


class NewsItem(BaseModel):
    title: str
    source: str = ""
    url: str = ""
    published: str = ""
    summary: str = ""


class InsiderTrade(BaseModel):
    """SEC Form 4 insider transaction from OpenInsider.com."""

    symbol: str
    insider_name: str
    title: str = ""
    trade_type: str = ""  # P - Purchase, S - Sale, etc.
    trade_date: str = ""
    filing_date: str = ""
    price: float | None = None
    quantity: int = 0
    shares_owned: int | None = None
    ownership_change_pct: float | None = None
    value: float | None = None
    source: str = "openinsider"

    @property
    def is_purchase(self) -> bool:
        return self.trade_type.upper().startswith("P")

    @property
    def is_sale(self) -> bool:
        return self.trade_type.upper().startswith("S")


class InsiderTradeSummary(BaseModel):
    symbol: str
    period_days: int = 90
    total_trades: int = 0
    purchases: int = 0
    sales: int = 0
    buy_value_usd: float = 0.0
    sell_value_usd: float = 0.0
    net_sentiment: str = "neutral"  # bullish, bearish, neutral
    notable_trades: list[InsiderTrade] = Field(default_factory=list)


class MarketSnapshot(BaseModel):
    symbol: str
    price: float | None = None
    change_pct: float | None = None
    volume: int | None = None
    market_cap: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    pe_ratio: float | None = None
    sector: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ResearchBundle(BaseModel):
    """All gathered intelligence for a symbol before AI analysis."""

    symbol: str
    asset_type: AssetType = AssetType.STOCK
    market: MarketSnapshot | None = None
    news: list[NewsItem] = Field(default_factory=list)
    insider_trades: list[InsiderTrade] = Field(default_factory=list)
    insider_summary: InsiderTradeSummary | None = None
    web_snippets: list[str] = Field(default_factory=list)
    technical_signals: dict[str, Any] = Field(default_factory=dict)
    gathered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TradeSignal(BaseModel):
    """AI-generated trading recommendation."""

    symbol: str
    action: TradeAction
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 confidence score")
    quantity: int = Field(ge=0, description="Suggested shares/contracts")
    limit_price: float | None = None
    reasoning: str
    risk_factors: list[str] = Field(default_factory=list)
    news_catalysts: list[str] = Field(default_factory=list)
    asset_type: AssetType = AssetType.STOCK
    platform: str = "paper"  # paper, robinhood, kalshi, polymarket
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradeExecutionResult(BaseModel):
    signal: TradeSignal
    executed: bool
    dry_run: bool
    platform: str
    order_id: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class TradingCycleReport(BaseModel):
    """Report from a full analyze-and-trade cycle."""

    symbols_analyzed: list[str]
    signals: list[TradeSignal]
    executions: list[TradeExecutionResult]
    research: list[ResearchBundle]
    summary: str


class TradeOpportunity(BaseModel):
    """A ranked trading opportunity found by scanning the market."""

    symbol: str
    name: str = ""
    action: TradeAction = TradeAction.BUY
    score: float = Field(default=0.0, description="Composite rank score, higher is better")
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    price: float | None = None
    change_pct: float | None = None
    price_target: float | None = None
    upside_pct: float | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    asset_type: AssetType = AssetType.STOCK
    platform: str = "paper"
    setup: str = ""  # e.g. "oversold bounce", "insider cluster buy", "momentum breakout"
    catalysts: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScanReport(BaseModel):
    """Result of a market-wide scan for the best trades."""

    scan_type: str = "stocks"
    universe_size: int = 0
    scanned: int = 0
    opportunities: list[TradeOpportunity] = Field(default_factory=list)
    summary: str = ""
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketPrediction(BaseModel):
    """Short-term market prediction with buy/sell timing."""

    symbol: str
    current_price: float
    price_target_1d: float | None = None
    price_target_1w: float | None = None
    direction: str = "neutral"  # bullish, bearish, neutral
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    recommended_action: TradeAction = TradeAction.HOLD
    buy_zone: float | None = None
    sell_zone: float | None = None
    support: float | None = None
    resistance: float | None = None
    momentum_score: float = 0.0
    sentiment_score: float = 0.0
    summary: str = ""
    factors: list[str] = Field(default_factory=list)
