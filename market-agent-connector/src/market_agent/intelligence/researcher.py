"""Unified intelligence gathering — combines market data, news, and web research."""

from __future__ import annotations

from market_agent.ai.models import AssetType, MarketSnapshot, ResearchBundle
from market_agent.intelligence.insider_fetcher import InsiderFetcher
from market_agent.intelligence.market_data import MarketDataFetcher
from market_agent.intelligence.news_fetcher import NewsFetcher
from market_agent.intelligence.web_research import WebResearcher


class IntelligenceResearcher:
    """Gathers all real-world data needed for AI trading decisions."""

    def __init__(
        self,
        finnhub_api_key: str = "",
    ) -> None:
        self.market_data = MarketDataFetcher()
        self.news = NewsFetcher(finnhub_api_key=finnhub_api_key)
        self.insider = InsiderFetcher(finnhub_api_key=finnhub_api_key)
        self.web = WebResearcher()

    async def close(self) -> None:
        await self.market_data.close()
        await self.news.close()
        await self.insider.close()
        await self.web.close()

    async def research_stock(self, symbol: str) -> ResearchBundle:
        symbol = symbol.upper().strip()
        market = await self._quote_or_none(symbol)
        technicals = await self.market_data.get_technicals(symbol)
        news = await self.news.get_stock_news(symbol, limit=12)
        insider_trades = await self.insider.get_trades(symbol, limit=15, days=180)
        insider_summary = await self.insider.get_summary(symbol, days=90)
        web_snippets = await self.web.research_symbol(symbol)

        return ResearchBundle(
            symbol=symbol,
            asset_type=AssetType.STOCK,
            market=market,
            news=news,
            insider_trades=insider_trades,
            insider_summary=insider_summary,
            web_snippets=web_snippets,
            technical_signals=technicals,
        )

    async def research_stock_fast(
        self, symbol: str, include_news: bool = False
    ) -> ResearchBundle:
        """Lightweight research for bulk scanning — technicals only by default.

        Skips insider scraping and web search, which are the slow calls, so a
        large universe can be screened without hammering upstream sources.
        """
        symbol = symbol.upper().strip()
        market = await self._quote_or_none(symbol)
        technicals = await self.market_data.get_technicals(symbol)
        if market is None and not technicals.get("current_price"):
            raise ValueError(f"No market data available for {symbol}")
        news = await self.news.get_stock_news(symbol, limit=5) if include_news else []

        return ResearchBundle(
            symbol=symbol,
            asset_type=AssetType.STOCK,
            market=market,
            news=news,
            technical_signals=technicals,
        )

    async def _quote_or_none(self, symbol: str) -> MarketSnapshot | None:
        """Quotes can be blocked upstream; technicals alone are still usable."""
        try:
            return await self.market_data.get_quote(symbol)
        except Exception:
            return None

    async def research_topic(self, query: str) -> ResearchBundle:
        """Research a general topic (e.g. 'Fed interest rate decision')."""
        news = await self.news.search_news(query, limit=15)
        web_snippets = await self.web.research(query)

        return ResearchBundle(
            symbol=query,
            asset_type=AssetType.PREDICTION,
            news=news,
            web_snippets=web_snippets,
        )
