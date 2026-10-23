"""Live stock market data from Yahoo Finance (no API key required)."""

from __future__ import annotations

import asyncio
from typing import Any

from market_agent.ai.models import MarketSnapshot
from market_agent.intelligence.yahoo import CHART_URL, QUOTE_URL, YahooSession

MAX_CONCURRENT_CHART_FETCHES = 8


class MarketDataFetcher:
    def __init__(self, session: YahooSession | None = None) -> None:
        self._session = session or YahooSession(timeout=20.0)
        self._owns_session = session is None

    @property
    def session(self) -> YahooSession:
        return self._session

    async def close(self) -> None:
        if self._owns_session:
            await self._session.close()

    async def get_quote(self, symbol: str) -> MarketSnapshot:
        """Fetch a quote, falling back to the chart API when quotes are blocked."""
        symbol = symbol.upper().strip()
        data = await self._session.get_json(
            QUOTE_URL, {"symbols": symbol}, needs_crumb=True
        )
        results = (data or {}).get("quoteResponse", {}).get("result", [])
        if results:
            return _snapshot_from_quote(results[0], symbol)

        snapshot = await self._quote_from_chart(symbol)
        if snapshot is None:
            raise ValueError(f"No market data found for {symbol}")
        return snapshot

    async def get_quotes(self, symbols: list[str]) -> list[MarketSnapshot]:
        if not symbols:
            return []
        wanted = [s.upper().strip() for s in symbols if s.strip()]
        data = await self._session.get_json(
            QUOTE_URL, {"symbols": ",".join(wanted)}, needs_crumb=True
        )
        results = (data or {}).get("quoteResponse", {}).get("result", [])
        snapshots = [
            _snapshot_from_quote(q, q.get("symbol", "")) for q in results if q.get("symbol")
        ]

        # Fill gaps (or a fully blocked batch request) from the chart API
        missing = [s for s in wanted if s not in {snap.symbol for snap in snapshots}]
        if missing:
            snapshots.extend(await self._quotes_from_charts(missing))
        return snapshots

    async def get_technicals(self, symbol: str, range_: str = "3mo") -> dict[str, Any]:
        """Compute simple technical indicators from price history."""
        symbol = symbol.upper().strip()
        data = await self._session.get_json(
            CHART_URL.format(symbol=symbol), {"range": range_, "interval": "1d"}
        )
        chart = (data or {}).get("chart", {}).get("result", [])
        if not chart:
            return {}

        meta = chart[0].get("meta", {})
        closes = chart[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c is not None]
        if len(closes) < 5:
            return {"current_price": meta.get("regularMarketPrice")}

        sma_20 = sum(closes[-20:]) / min(20, len(closes))
        sma_50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 10 else None
        current = closes[-1]

        # RSI (14-period simplified)
        rsi = _compute_rsi(closes[-15:]) if len(closes) >= 15 else None

        trend = "bullish" if current > sma_20 else "bearish"
        if sma_50:
            if current > sma_20 > sma_50:
                trend = "strong_bullish"
            elif current < sma_20 < sma_50:
                trend = "strong_bearish"

        return {
            "current_price": current,
            "sma_20": round(sma_20, 2),
            "sma_50": round(sma_50, 2) if sma_50 else None,
            "rsi_14": round(rsi, 1) if rsi else None,
            "trend": trend,
            "day_change_pct": meta.get("regularMarketChangePercent"),
            "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        }

    async def _quote_from_chart(self, symbol: str) -> MarketSnapshot | None:
        data = await self._session.get_json(
            CHART_URL.format(symbol=symbol), {"range": "5d", "interval": "1d"}
        )
        chart = (data or {}).get("chart", {}).get("result", [])
        if not chart:
            return None
        return _snapshot_from_chart_meta(chart[0].get("meta", {}), symbol)

    async def _quotes_from_charts(self, symbols: list[str]) -> list[MarketSnapshot]:
        sem = asyncio.Semaphore(MAX_CONCURRENT_CHART_FETCHES)

        async def one(sym: str) -> MarketSnapshot | None:
            async with sem:
                return await self._quote_from_chart(sym)

        results = await asyncio.gather(
            *(one(s) for s in symbols), return_exceptions=True
        )
        return [r for r in results if isinstance(r, MarketSnapshot)]


def _snapshot_from_quote(q: dict[str, Any], symbol: str) -> MarketSnapshot:
    price = q.get("regularMarketPrice") or q.get("postMarketPrice")
    prev = q.get("regularMarketPreviousClose") or price
    change_pct = q.get("regularMarketChangePercent")
    if change_pct is None and price and prev:
        change_pct = ((price - prev) / prev) * 100

    return MarketSnapshot(
        symbol=(q.get("symbol") or symbol).upper(),
        price=price,
        change_pct=round(change_pct, 2) if change_pct is not None else None,
        volume=q.get("regularMarketVolume"),
        market_cap=q.get("marketCap"),
        fifty_two_week_high=q.get("fiftyTwoWeekHigh"),
        fifty_two_week_low=q.get("fiftyTwoWeekLow"),
        pe_ratio=q.get("trailingPE") or q.get("forwardPE"),
        sector=q.get("sector", ""),
        extra={
            "name": q.get("shortName") or q.get("longName", ""),
            "exchange": q.get("fullExchangeName", ""),
            "currency": q.get("currency", "USD"),
            "source": "yahoo_quote",
        },
    )


def _snapshot_from_chart_meta(meta: dict[str, Any], symbol: str) -> MarketSnapshot | None:
    """Build a snapshot from chart metadata.

    The chart endpoint needs no crumb, so it keeps price data flowing when the
    quote API is unavailable. It carries no market cap or P/E ratio.
    """
    price = meta.get("regularMarketPrice")
    if price is None:
        return None
    prev = meta.get("previousClose") or meta.get("chartPreviousClose")
    change_pct = ((price - prev) / prev) * 100 if prev else None

    return MarketSnapshot(
        symbol=(meta.get("symbol") or symbol).upper(),
        price=price,
        change_pct=round(change_pct, 2) if change_pct is not None else None,
        volume=meta.get("regularMarketVolume"),
        fifty_two_week_high=meta.get("fiftyTwoWeekHigh"),
        fifty_two_week_low=meta.get("fiftyTwoWeekLow"),
        extra={
            "name": meta.get("longName") or meta.get("shortName", ""),
            "exchange": meta.get("fullExchangeName", ""),
            "currency": meta.get("currency", "USD"),
            "source": "yahoo_chart",
        },
    )


def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
