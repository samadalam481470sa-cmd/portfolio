"""Tests for the opportunity scanner and market screener."""

from __future__ import annotations

import pytest

from market_agent.ai.market_predictor import MarketPredictor
from market_agent.ai.models import (
    AssetType,
    MarketSnapshot,
    ResearchBundle,
    TradeAction,
)
from market_agent.ai.opportunity_scanner import (
    OpportunityScanner,
    _risk_levels,
    _summarize,
    _to_opportunity,
)
from market_agent.intelligence.screener import DEFAULT_UNIVERSE, SECTOR_TICKERS, _to_snapshot


class FakeResearcher:
    """Stands in for IntelligenceResearcher with deterministic data."""

    def __init__(self, data: dict[str, dict]) -> None:
        self.data = data
        self.insider = self

    async def research_stock_fast(self, symbol: str, include_news: bool = False) -> ResearchBundle:
        entry = self.data.get(symbol)
        if entry is None:
            raise ValueError(f"no data for {symbol}")
        return ResearchBundle(
            symbol=symbol,
            asset_type=AssetType.STOCK,
            market=MarketSnapshot(
                symbol=symbol,
                price=entry["price"],
                change_pct=entry.get("change_pct", 0.0),
                volume=entry.get("volume", 5_000_000),
            ),
            technical_signals={
                "current_price": entry["price"],
                "rsi_14": entry["rsi"],
                "sma_20": entry["sma20"],
                "sma_50": entry["sma50"],
                "trend": entry["trend"],
            },
        )

    async def get_cluster_buys(self, days: int = 14, min_insiders: int = 2, limit: int = 20):
        return [
            {
                "symbol": "OSCR",
                "insider_count": 4,
                "trade_count": 5,
                "total_value_usd": 1_500_000.0,
                "insiders": ["Jane Doe", "John Roe"],
                "latest_date": "2026-08-14",
                "trades": [],
            }
        ]


class FakeScreener:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def trending(self, limit: int = 15) -> list[str]:
        return ["OVERSOLD", "STRONG", "WEAK"][:limit]

    async def get_universe_quotes(self, symbols=None):
        return [
            MarketSnapshot(symbol=s, price=25.0, change_pct=1.0, volume=3_000_000)
            for s in (symbols or [])
        ]

    async def top_gainers(self, limit: int = 10, symbols=None):
        return [MarketSnapshot(symbol="STRONG", price=110.0, change_pct=6.0)]

    async def top_losers(self, limit: int = 10, symbols=None):
        return [MarketSnapshot(symbol="OVERSOLD", price=50.0, change_pct=-5.0)]

    async def most_active(self, limit: int = 10, symbols=None):
        return [MarketSnapshot(symbol="WEAK", price=80.0, volume=90_000_000)]

    async def sector_universe(self, sector: str) -> list[str]:
        return SECTOR_TICKERS.get(sector.lower(), [])


FIXTURES = {
    # Deeply oversold but in an uptrend -> strong buy candidate
    "OVERSOLD": {
        "price": 50.0,
        "rsi": 22.0,
        "sma20": 56.0,
        "sma50": 54.0,
        "trend": "bullish",
        "change_pct": -4.0,
    },
    # Momentum leader
    "STRONG": {
        "price": 110.0,
        "rsi": 58.0,
        "sma20": 105.0,
        "sma50": 100.0,
        "trend": "strong_bullish",
        "change_pct": 2.5,
    },
    # Overbought downtrend -> sell candidate
    "WEAK": {
        "price": 80.0,
        "rsi": 78.0,
        "sma20": 90.0,
        "sma50": 95.0,
        "trend": "strong_bearish",
        "change_pct": -3.0,
    },
}


def make_scanner() -> OpportunityScanner:
    return OpportunityScanner(
        researcher=FakeResearcher(FIXTURES),
        predictor=MarketPredictor(),
        screener=FakeScreener(),
    )


@pytest.mark.asyncio
async def test_scan_stocks_ranks_and_excludes_holds():
    report = await make_scanner().scan_stocks(
        symbols=["OVERSOLD", "STRONG", "WEAK"], limit=5
    )

    assert report.scan_type == "stocks"
    assert report.universe_size == 3
    assert report.opportunities, "expected at least one actionable setup"
    # Ranked descending by score
    scores = [o.score for o in report.opportunities]
    assert scores == sorted(scores, reverse=True)
    # HOLD setups are filtered out of the default scan
    assert all(o.action != TradeAction.HOLD for o in report.opportunities)


@pytest.mark.asyncio
async def test_scan_stocks_action_filter():
    report = await make_scanner().scan_stocks(
        symbols=["OVERSOLD", "STRONG", "WEAK"], action="sell", limit=5
    )
    assert all(o.action == TradeAction.SELL for o in report.opportunities)


@pytest.mark.asyncio
async def test_scan_stocks_action_all_keeps_holds():
    scanner = make_scanner()
    scanner.researcher.data["FLAT"] = {
        "price": 15.0,
        "rsi": 50.0,
        "sma20": 15.1,
        "sma50": 15.0,
        "trend": "neutral",
        "change_pct": 0.1,
    }
    report = await scanner.scan_stocks(symbols=["FLAT"], action="all")
    assert [o.action for o in report.opportunities] == [TradeAction.HOLD]

    filtered = await scanner.scan_stocks(symbols=["FLAT"], action="any")
    assert filtered.opportunities == []


@pytest.mark.asyncio
async def test_scan_stocks_survives_bad_symbols():
    report = await make_scanner().scan_stocks(symbols=["STRONG", "NOPE"], limit=5)
    assert report.scanned == 1
    assert all(o.symbol != "NOPE" for o in report.opportunities)


@pytest.mark.asyncio
async def test_scan_stocks_dedupes_universe():
    report = await make_scanner().scan_stocks(symbols=["STRONG", "strong", "STRONG"])
    assert report.universe_size == 1


@pytest.mark.asyncio
async def test_min_score_filter():
    report = await make_scanner().scan_stocks(
        symbols=["OVERSOLD", "STRONG", "WEAK"], min_score=10_000
    )
    assert report.opportunities == []
    assert "no setups" in report.summary


@pytest.mark.asyncio
async def test_total_data_failure_is_reported_as_such():
    """A blocked price feed must not look like 'nothing worth trading'."""
    report = await make_scanner().scan_stocks(symbols=["NOPE1", "NOPE2"])
    assert report.scanned == 0
    assert report.opportunities == []
    assert "Could not retrieve market data" in report.summary
    assert "no setups" not in report.summary


@pytest.mark.asyncio
async def test_partial_data_failure_is_disclosed():
    report = await make_scanner().scan_stocks(symbols=["STRONG", "NOPE"], min_score=10_000)
    assert "1 of 2 symbols" in report.summary


@pytest.mark.asyncio
async def test_find_best_trades_adds_catalysts_and_insider_bonus():
    scanner = make_scanner()
    # The insider cluster symbol needs price data to be scored
    scanner.researcher.data["OSCR"] = {
        "price": 15.0,
        "rsi": 33.0,
        "sma20": 16.0,
        "sma50": 15.5,
        "trend": "bullish",
        "change_pct": 1.0,
    }

    report = await scanner.find_best_trades(limit=5)
    assert report.scan_type == "best_trades"
    by_symbol = {o.symbol: o for o in report.opportunities}

    assert "OSCR" in by_symbol
    oscr = by_symbol["OSCR"]
    assert oscr.metadata["insider_cluster"]["insider_count"] == 4
    assert any("insiders bought" in c for c in oscr.catalysts)

    assert any("top gainer" in c for c in by_symbol["STRONG"].catalysts)


@pytest.mark.asyncio
async def test_scan_insider_buys_builds_levels():
    report = await make_scanner().scan_insider_buys(days=14, min_insiders=2)
    assert len(report.opportunities) == 1
    opp = report.opportunities[0]
    assert opp.symbol == "OSCR"
    assert opp.action == TradeAction.BUY
    assert opp.setup == "insider cluster buy"
    assert opp.stop_loss and opp.take_profit
    assert opp.stop_loss < opp.price < opp.take_profit


@pytest.mark.asyncio
async def test_compare_returns_ranked_list():
    ranked = await make_scanner().compare(["weak", "strong"])
    assert [o.symbol for o in ranked] == sorted(
        [o.symbol for o in ranked], key=lambda s: -next(x.score for x in ranked if x.symbol == s)
    )
    assert len(ranked) == 2


@pytest.mark.asyncio
async def test_scan_sector_uses_sector_universe():
    scanner = make_scanner()
    scanner.researcher.data["NVDA"] = FIXTURES["STRONG"]
    report = await scanner.scan_sector("ai", limit=3)
    assert report.scan_type == "sector:ai"
    assert report.universe_size == len(SECTOR_TICKERS["ai"])


@pytest.mark.asyncio
async def test_prediction_scan_without_connectors_is_empty():
    report = await make_scanner().find_prediction_opportunities(platform="kalshi")
    assert report.opportunities == []
    assert "No qualifying" in report.summary


class FakeKalshi:
    def __init__(self, markets: list[dict]) -> None:
        self.markets = markets

    async def list_markets(self, limit: int = 200, status: str = "open") -> dict:
        return {"markets": self.markets}


@pytest.mark.asyncio
async def test_kalshi_scan_finds_carry_and_spread_trades():
    scanner = make_scanner()
    scanner.kalshi = FakeKalshi([
        # 96c YES: high-probability carry
        {"ticker": "CARRY-1", "title": "Will X happen?", "yes_bid": 95, "yes_ask": 96, "volume": 50_000},
        # Wide spread
        {"ticker": "SPREAD-1", "title": "Coin flip", "yes_bid": 40, "yes_ask": 50, "volume": 20_000},
        # Illiquid, should be skipped entirely
        {"ticker": "THIN-1", "title": "Nobody trades this", "yes_bid": 10, "yes_ask": 90, "volume": 5},
    ])

    report = await scanner.find_prediction_opportunities(platform="kalshi", limit=10)
    tickers = {o.symbol for o in report.opportunities}
    assert "CARRY-1" in tickers
    assert "SPREAD-1" in tickers
    assert "THIN-1" not in tickers
    assert all(o.asset_type == AssetType.PREDICTION for o in report.opportunities)
    assert all(o.platform == "kalshi" for o in report.opportunities)

    spread = next(o for o in report.opportunities if o.symbol == "SPREAD-1")
    assert "spread" in spread.setup


class FakePolymarket:
    async def list_markets(self, **kwargs) -> list[dict]:
        return [
            {
                "conditionId": "0xabc",
                "question": "Will the Fed cut rates?",
                "outcomePrices": '["0.94", "0.06"]',
                "volume24hr": 250_000,
                "slug": "fed-cut",
            },
            {
                "conditionId": "0xdef",
                "question": "Toss up market",
                "outcomePrices": '["0.51", "0.49"]',
                "volume24hr": 900_000,
            },
        ]


@pytest.mark.asyncio
async def test_polymarket_scan_selects_favourites_only():
    scanner = make_scanner()
    scanner.polymarket = FakePolymarket()
    report = await scanner.find_prediction_opportunities(platform="polymarket", limit=10)
    assert [o.symbol for o in report.opportunities] == ["0xabc"]
    assert report.opportunities[0].platform == "polymarket"


@pytest.mark.asyncio
async def test_scanner_close_closes_screener():
    scanner = make_scanner()
    await scanner.close()
    assert scanner.screener.closed


# ── Pure helpers ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_to_opportunity_flags_thin_volume():
    research = ResearchBundle(
        symbol="THIN",
        market=MarketSnapshot(symbol="THIN", price=10.0, change_pct=1.0, volume=50_000),
        technical_signals={"current_price": 10.0, "rsi_14": 25.0, "sma_20": 11.0, "trend": "bullish"},
    )
    prediction = await MarketPredictor().predict(research)
    opp = _to_opportunity("THIN", research, prediction)
    assert any("Thin volume" in w for w in opp.warnings)


def test_risk_levels_buy_and_sell_orientation():
    from market_agent.ai.models import MarketPrediction

    prediction = MarketPrediction(
        symbol="X",
        current_price=100.0,
        support=95.0,
        resistance=110.0,
        sell_zone=108.0,
        buy_zone=96.0,
    )

    stop, target, rr = _risk_levels(100.0, TradeAction.BUY, prediction)
    assert stop < 100.0 < target
    assert rr and rr > 0

    stop, target, rr = _risk_levels(100.0, TradeAction.SELL, prediction)
    assert target < 100.0 < stop
    assert rr and rr > 0


def test_risk_levels_without_price():
    from market_agent.ai.models import MarketPrediction

    assert _risk_levels(None, TradeAction.BUY, MarketPrediction(symbol="X", current_price=0)) == (
        None,
        None,
        None,
    )


def test_summarize_empty_and_populated():
    from market_agent.ai.models import TradeOpportunity

    assert "no setups" in _summarize([], 25)
    summary = _summarize(
        [TradeOpportunity(symbol="AAPL", action=TradeAction.BUY, score=72.0, confidence=0.7)], 25
    )
    assert "AAPL" in summary and "BUY" in summary


def test_screener_snapshot_parsing():
    snap = _to_snapshot({
        "symbol": "aapl",
        "regularMarketPrice": 200.0,
        "regularMarketPreviousClose": 190.0,
        "regularMarketVolume": 1_000_000,
        "shortName": "Apple Inc.",
    })
    assert snap is not None
    assert snap.symbol == "AAPL"
    assert snap.change_pct == pytest.approx(5.26, abs=0.01)
    assert snap.extra["name"] == "Apple Inc."

    assert _to_snapshot({"regularMarketPrice": 1.0}) is None


def test_default_universe_is_unique():
    assert len(DEFAULT_UNIVERSE) == len(set(DEFAULT_UNIVERSE))


@pytest.mark.asyncio
async def test_movers_only_return_the_correct_direction():
    """The universe fallback contains both directions, so signs must be filtered."""
    from market_agent.intelligence.screener import MarketScreener

    mixed = [
        MarketSnapshot(symbol="UP1", price=10.0, change_pct=4.0, volume=1_000),
        MarketSnapshot(symbol="UP2", price=10.0, change_pct=1.0, volume=9_000),
        MarketSnapshot(symbol="DOWN1", price=10.0, change_pct=-3.0, volume=5_000),
        MarketSnapshot(symbol="FLAT", price=10.0, change_pct=None, volume=7_000),
    ]

    screener = MarketScreener.__new__(MarketScreener)

    async def fake_lookup(scr_id, symbols):
        return mixed

    screener._screener_or_universe = fake_lookup  # type: ignore[method-assign]

    gainers = await screener.top_gainers(limit=5)
    assert [q.symbol for q in gainers] == ["UP1", "UP2"]

    losers = await screener.top_losers(limit=5)
    assert [q.symbol for q in losers] == ["DOWN1"]

    active = await screener.most_active(limit=5)
    assert [q.symbol for q in active] == ["UP2", "FLAT", "DOWN1", "UP1"]


def test_summarize_pluralizes_and_breaks_down_actions():
    from market_agent.ai.models import TradeOpportunity

    single = _summarize(
        [TradeOpportunity(symbol="AAPL", action=TradeAction.BUY, score=50.0)], 10
    )
    assert "1 opportunity" in single

    many = _summarize(
        [
            TradeOpportunity(symbol="AAPL", action=TradeAction.BUY, score=50.0),
            TradeOpportunity(symbol="NVDA", action=TradeAction.SELL, score=40.0),
            TradeOpportunity(symbol="MSFT", action=TradeAction.HOLD, score=10.0),
        ],
        10,
    )
    assert "3 opportunities" in many
    assert "1 buy" in many and "1 sell" in many and "1 hold" in many
