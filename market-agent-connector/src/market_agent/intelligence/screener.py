"""Market screener — discover movers, trending stocks, and scan universes."""

from __future__ import annotations

from typing import Any

from market_agent.ai.models import MarketSnapshot
from market_agent.intelligence.market_data import MarketDataFetcher
from market_agent.intelligence.yahoo import SCREENER_URL, TRENDING_URL, YahooSession

FALLBACK_UNIVERSE_LIMIT = 40

# Liquid large/mid-cap universe used as a reliable fallback for scanning
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "AMD", "NFLX",
    "JPM", "V", "MA", "UNH", "XOM", "JNJ", "WMT", "PG", "HD", "COST",
    "ORCL", "CRM", "ADBE", "INTC", "CSCO", "QCOM", "TXN", "MU", "PLTR", "UBER",
    "BAC", "WFC", "GS", "MS", "C", "PFE", "MRK", "ABBV", "LLY", "TMO",
    "DIS", "CMCSA", "T", "VZ", "KO", "PEP", "MCD", "NKE", "SBUX", "BA",
    "CAT", "DE", "GE", "HON", "LMT", "RTX", "UPS", "FDX", "CVX", "COP",
    "SHOP", "SQ", "PYPL", "COIN", "HOOD", "SOFI", "RIVN", "LCID", "F", "GM",
    "SPY", "QQQ", "IWM", "DIA", "ARKK",
]

SECTOR_TICKERS = {
    "tech": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "AMD", "ORCL", "CRM", "ADBE"],
    "finance": ["JPM", "BAC", "WFC", "GS", "MS", "C", "V", "MA", "AXP", "BLK"],
    "healthcare": ["UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO", "ABT", "DHR", "BMY"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HES"],
    "consumer": ["AMZN", "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "PG"],
    "crypto": ["COIN", "MSTR", "MARA", "RIOT", "HOOD", "CLSK", "HUT"],
    "ai": ["NVDA", "AMD", "PLTR", "SMCI", "MU", "AVGO", "TSM", "ARM", "MRVL"],
}


class MarketScreener:
    """Find market opportunities: gainers, losers, most active, trending."""

    def __init__(self, session: YahooSession | None = None) -> None:
        self._session = session or YahooSession()
        self._owns_session = session is None
        self._market_data = MarketDataFetcher(self._session)

    async def close(self) -> None:
        if self._owns_session:
            await self._session.close()

    async def get_universe_quotes(self, symbols: list[str] | None = None) -> list[MarketSnapshot]:
        """Batch-fetch quotes for a universe of symbols."""
        universe = [s.upper() for s in (symbols if symbols is not None else DEFAULT_UNIVERSE)]
        snapshots: list[MarketSnapshot] = []

        # Yahoo caps symbols per request; chunk them
        for i in range(0, len(universe), 40):
            chunk = universe[i : i + 40]
            try:
                snapshots.extend(await self._market_data.get_quotes(chunk))
            except Exception:
                continue

        return snapshots

    async def top_gainers(self, limit: int = 10, symbols: list[str] | None = None) -> list[MarketSnapshot]:
        quotes = await self._screener_or_universe("day_gainers", symbols)
        # A "gainer" must actually be up; the universe fallback contains both sides
        ranked = sorted(
            [q for q in quotes if q.change_pct is not None and q.change_pct > 0],
            key=lambda q: q.change_pct or 0,
            reverse=True,
        )
        return ranked[:limit]

    async def top_losers(self, limit: int = 10, symbols: list[str] | None = None) -> list[MarketSnapshot]:
        quotes = await self._screener_or_universe("day_losers", symbols)
        ranked = sorted(
            [q for q in quotes if q.change_pct is not None and q.change_pct < 0],
            key=lambda q: q.change_pct or 0,
        )
        return ranked[:limit]

    async def most_active(self, limit: int = 10, symbols: list[str] | None = None) -> list[MarketSnapshot]:
        quotes = await self._screener_or_universe("most_actives", symbols)
        ranked = sorted(
            [q for q in quotes if q.volume],
            key=lambda q: q.volume or 0,
            reverse=True,
        )
        return ranked[:limit]

    async def trending(self, limit: int = 15) -> list[str]:
        """Get trending tickers from Yahoo, falling back to a liquid universe."""
        data = await self._session.get_json(TRENDING_URL, {"count": limit})
        result = (data or {}).get("finance", {}).get("result", [])
        if result:
            symbols = [
                q.get("symbol", "") for q in result[0].get("quotes", []) if q.get("symbol")
            ]
            if symbols:
                return symbols[:limit]
        return DEFAULT_UNIVERSE[:limit]

    async def sector_universe(self, sector: str) -> list[str]:
        return SECTOR_TICKERS.get(sector.lower(), DEFAULT_UNIVERSE[:20])

    async def _screener_or_universe(
        self, scr_id: str, symbols: list[str] | None
    ) -> list[MarketSnapshot]:
        """Try Yahoo's predefined screener; fall back to scanning our universe."""
        if symbols is None:
            data = await self._session.get_json(
                SCREENER_URL, {"scrIds": scr_id, "count": 50}
            )
            result = (data or {}).get("finance", {}).get("result", [])
            if result:
                snaps = [_to_snapshot(q) for q in result[0].get("quotes", [])]
                valid = [s for s in snaps if s]
                if valid:
                    return valid
        # Fall back to a trimmed universe: the fallback path may need one request
        # per symbol, so scanning the full list is needlessly slow.
        return await self.get_universe_quotes(
            symbols if symbols is not None else DEFAULT_UNIVERSE[:FALLBACK_UNIVERSE_LIMIT]
        )


def _to_snapshot(q: dict[str, Any]) -> MarketSnapshot | None:
    symbol = q.get("symbol")
    if not symbol:
        return None
    price = q.get("regularMarketPrice") or q.get("postMarketPrice")
    prev = q.get("regularMarketPreviousClose") or price
    change_pct = q.get("regularMarketChangePercent")
    if change_pct is None and price and prev:
        change_pct = round(((price - prev) / prev) * 100, 2)
    return MarketSnapshot(
        symbol=symbol.upper(),
        price=price,
        change_pct=round(change_pct, 2) if change_pct is not None else None,
        volume=q.get("regularMarketVolume"),
        market_cap=q.get("marketCap"),
        fifty_two_week_high=q.get("fiftyTwoWeekHigh"),
        fifty_two_week_low=q.get("fiftyTwoWeekLow"),
        pe_ratio=q.get("trailingPE") or q.get("forwardPE"),
        sector=q.get("sector", ""),
        extra={"name": q.get("shortName") or q.get("longName", "")},
    )
