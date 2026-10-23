"""MCP server exposing market platform tools for AI agents."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from market_agent.ai.opportunity_scanner import OpportunityScanner
from market_agent.config import load_settings
from market_agent.connectors import KalshiConnector, PolymarketConnector, RobinhoodConnector
from market_agent.trader.auto_trader import AutoTrader
from market_agent.growth.growth_trader import GrowthTrader

settings = load_settings()
polymarket = PolymarketConnector(settings.polymarket)
kalshi = KalshiConnector(settings.kalshi)
robinhood = RobinhoodConnector(settings.robinhood)
trader = AutoTrader(settings)
growth_trader = GrowthTrader(settings)
scanner = OpportunityScanner(
    researcher=trader.researcher, kalshi=kalshi, polymarket=polymarket
)

mcp = FastMCP(
    "Market Agent Connector",
    instructions=(
        "Connects AI agents to Polymarket, Kalshi, and Robinhood prediction/trading platforms. "
        "Includes an advanced AI trading engine that fetches live market data, news, and web research "
        "to make buy/sell/hold decisions. Use ai_* tools for intelligent trading. "
        "Use find_best_trades and scan_* tools to discover which trades to make. "
        "Use polymarket_* tools for Polymarket, kalshi_* for Kalshi, robinhood_* for Robinhood. "
        "Paper trading works out of the box; live trading requires platform credentials in .env."
    ),
)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


# ── Health & status ──────────────────────────────────────────────────────────


@mcp.tool()
async def connector_status() -> str:
    """Check health and authentication status for all connected platforms."""
    results = {
        "polymarket": await polymarket.health(),
        "kalshi": await kalshi.health(),
        "robinhood": await robinhood.health(),
    }
    return _json(results)


# ── Polymarket tools ─────────────────────────────────────────────────────────


@mcp.tool()
async def polymarket_search_markets(query: str, limit: int = 10) -> str:
    """Search Polymarket for events and markets by keyword."""
    return _json(await polymarket.search_markets(query, limit))


@mcp.tool()
async def polymarket_list_events(limit: int = 20, active: bool = True, tag: str = "") -> str:
    """List Polymarket events. Optionally filter by tag slug (e.g. 'politics', 'sports')."""
    return _json(await polymarket.list_events(limit, active, tag or None))


@mcp.tool()
async def polymarket_get_event(slug: str) -> str:
    """Get a Polymarket event by URL slug (e.g. 'will-trump-win-2024')."""
    return _json(await polymarket.get_event(slug))


@mcp.tool()
async def polymarket_get_orderbook(token_id: str) -> str:
    """Get Polymarket CLOB orderbook for a token ID (from clobTokenIds on a market)."""
    return _json(await polymarket.get_orderbook(token_id))


@mcp.tool()
async def polymarket_get_price(token_id: str, side: str = "buy") -> str:
    """Get current Polymarket price for a token. Side is 'buy' or 'sell'."""
    return _json(await polymarket.get_price(token_id, side))


@mcp.tool()
async def polymarket_get_positions(user_address: str = "") -> str:
    """Get Polymarket positions for a wallet address (uses configured wallet if empty)."""
    return _json(await polymarket.get_positions(user_address or None))


@mcp.tool()
async def polymarket_place_order(
    token_id: str,
    price: float,
    size: float,
    side: str,
) -> str:
    """Place a Polymarket limit order. Requires CLOB API credentials in .env.

    Args:
        token_id: CLOB token ID from market clobTokenIds
        price: Limit price 0.01-0.99
        size: Number of shares
        side: 'BUY' or 'SELL'
    """
    return _json(await polymarket.place_limit_order(token_id, price, size, side))


@mcp.tool()
async def polymarket_cancel_order(order_id: str) -> str:
    """Cancel a Polymarket open order by ID. Requires CLOB API credentials."""
    return _json(await polymarket.cancel_order(order_id))


@mcp.tool()
async def polymarket_get_open_orders() -> str:
    """List all open Polymarket orders. Requires CLOB API credentials."""
    return _json(await polymarket.get_open_orders())


# ── Kalshi tools ─────────────────────────────────────────────────────────────


@mcp.tool()
async def kalshi_list_events(limit: int = 20, status: str = "") -> str:
    """List Kalshi events. Status filter: unopened, open, closed, settled."""
    return _json(await kalshi.list_events(limit, status or None))


@mcp.tool()
async def kalshi_get_event(event_ticker: str) -> str:
    """Get a Kalshi event by ticker (e.g. 'KXHIGHNY-24JAN01')."""
    return _json(await kalshi.get_event(event_ticker))


@mcp.tool()
async def kalshi_list_markets(limit: int = 20, status: str = "open", event_ticker: str = "") -> str:
    """List Kalshi markets. Filter by status and/or parent event ticker."""
    return _json(await kalshi.list_markets(limit, status, event_ticker or None))


@mcp.tool()
async def kalshi_get_market(ticker: str) -> str:
    """Get a Kalshi market by ticker."""
    return _json(await kalshi.get_market(ticker))


@mcp.tool()
async def kalshi_get_orderbook(ticker: str, depth: int = 10) -> str:
    """Get Kalshi orderbook for a market ticker."""
    return _json(await kalshi.get_orderbook(ticker, depth))


@mcp.tool()
async def kalshi_get_balance() -> str:
    """Get Kalshi account balance. Requires API key credentials in .env."""
    return _json(await kalshi.get_balance())


@mcp.tool()
async def kalshi_get_positions(ticker: str = "") -> str:
    """Get Kalshi portfolio positions. Requires API key credentials."""
    return _json(await kalshi.get_positions(ticker or None))


@mcp.tool()
async def kalshi_place_order(
    ticker: str,
    side: str,
    action: str,
    count: int,
    yes_price: int = 0,
    no_price: int = 0,
) -> str:
    """Place a Kalshi order. Requires API key credentials in .env.

    Args:
        ticker: Market ticker
        side: 'yes' or 'no'
        action: 'buy' or 'sell'
        count: Number of contracts
        yes_price: Limit price in cents (1-99) for yes side, 0 for market
        no_price: Limit price in cents (1-99) for no side, 0 for market
    """
    return _json(
        await kalshi.create_order(
            ticker,
            side,
            action,
            count,
            yes_price=yes_price or None,
            no_price=no_price or None,
        )
    )


@mcp.tool()
async def kalshi_cancel_order(order_id: str) -> str:
    """Cancel a Kalshi order by ID. Requires API key credentials."""
    return _json(await kalshi.cancel_order(order_id))


# ── Robinhood tools ──────────────────────────────────────────────────────────


@mcp.tool()
async def robinhood_get_auth_url(state: str = "market-agent") -> str:
    """Get Robinhood OAuth authorization URL. User must visit this URL to grant access.
    Requires approved Partner API credentials (ROBINHOOD_CLIENT_ID)."""
    return robinhood.get_authorization_url(state)


@mcp.tool()
async def robinhood_exchange_code(code: str) -> str:
    """Exchange Robinhood OAuth authorization code for access tokens."""
    return _json(await robinhood.exchange_code(code))


@mcp.tool()
async def robinhood_get_account() -> str:
    """Get Robinhood account info. Requires OAuth access token."""
    return _json(await robinhood.get_account())


@mcp.tool()
async def robinhood_get_portfolio() -> str:
    """Get Robinhood portfolio summary. Requires OAuth access token."""
    return _json(await robinhood.get_portfolio())


@mcp.tool()
async def robinhood_get_positions() -> str:
    """Get Robinhood stock positions. Requires OAuth access token."""
    return _json(await robinhood.get_positions())


@mcp.tool()
async def robinhood_get_quotes(symbols: str) -> str:
    """Get Robinhood stock quotes. Pass comma-separated symbols (e.g. 'AAPL,TSLA,MSFT')."""
    return _json(await robinhood.get_quotes([s.strip() for s in symbols.split(",")]))


# ── AI Trading Intelligence tools ────────────────────────────────────────────


@mcp.tool()
async def ai_get_stock_quote(symbol: str) -> str:
    """Get live stock quote with price, volume, sector, and daily change from Yahoo Finance."""
    research = await trader.research(symbol)
    return _json(research.market.model_dump() if research.market else {})


@mcp.tool()
async def ai_get_stock_news(symbol: str, limit: int = 10) -> str:
    """Fetch real-time news about a stock from Google News RSS and Finnhub (if configured)."""
    news = await trader.researcher.news.get_stock_news(symbol, limit)
    return _json([n.model_dump() for n in news])


@mcp.tool()
async def ai_get_technicals(symbol: str) -> str:
    """Get technical indicators: SMA, RSI, trend analysis for a stock."""
    tech = await trader.researcher.market_data.get_technicals(symbol)
    return _json(tech)


@mcp.tool()
async def ai_research_symbol(symbol: str) -> str:
    """Full intelligence gathering: live price, news, web research, and technicals for a stock."""
    research = await trader.research(symbol)
    return _json(research.model_dump())


@mcp.tool()
async def ai_analyze_trade(symbol: str, platform: str = "paper") -> str:
    """AI analyzes a stock using live data + news + technicals and returns a buy/sell/hold signal.
    Uses GPT/LLM if AI_API_KEY is set, otherwise uses rule-based analysis."""
    research, signal = await trader.analyze(symbol, platform=platform)
    return _json({
        "signal": signal.model_dump(),
        "market_price": research.market.price if research.market else None,
        "news_count": len(research.news),
        "engine": "llm" if trader.llm and trader.llm.is_configured else "rules",
    })


@mcp.tool()
async def ai_execute_trade(
    symbol: str,
    platform: str = "paper",
    force: bool = False,
) -> str:
    """Research → AI analyze → execute trade. Respects risk limits and dry-run mode.
    Set force=true to bypass dry-run/confirmation. Platforms: paper, robinhood, kalshi."""
    _, signal = await trader.analyze(symbol, platform=platform)
    result = await trader.execute_signal(signal, force=force, platform=platform)
    return _json(result.model_dump())


@mcp.tool()
async def ai_run_trading_cycle(
    symbols: str = "",
    platform: str = "paper",
    force: bool = False,
) -> str:
    """Run full AI trading cycle on a watchlist: research all → analyze → execute trades.
    Pass comma-separated symbols or leave empty for default watchlist."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    report = await trader.run_cycle(symbols=symbol_list, platform=platform, force=force)
    return _json(report.model_dump())


@mcp.tool()
async def ai_get_paper_portfolio() -> str:
    """Get paper trading portfolio: cash, positions, P&L, and total value."""
    return _json(await trader.get_paper_portfolio())


@mcp.tool()
async def ai_get_insider_trades(symbol: str, days: int = 180) -> str:
    """Fetch insider trade history from OpenInsider.com (SEC Form 4 filings).
    Shows executive/director buys and sells with dollar values and sentiment."""
    summary = await trader.researcher.insider.get_summary(symbol, days=days)
    trades = await trader.researcher.insider.get_trades(symbol, limit=20, days=days)
    return _json({
        "summary": summary.model_dump(),
        "trades": [t.model_dump() for t in trades],
        "source": "openinsider.com (SEC Form 4)",
    })


@mcp.tool()
async def ai_search_web(query: str) -> str:
    """Search the web for real-world information about any topic (news, events, companies)."""
    snippets = await trader.researcher.web.research(query)
    return _json({"query": query, "snippets": snippets})


# ── Opportunity discovery (find the best trades) ───────────────────────────────


@mcp.tool()
async def find_best_trades(limit: int = 10, deep: bool = False) -> str:
    """Find the best trades to make right now. Scans top gainers/losers, most active,
    trending tickers and insider-buy clusters, then ranks every candidate by conviction
    with concrete entry, stop-loss and take-profit levels. Set deep=true to also pull
    news for each candidate (slower but more accurate)."""
    report = await scanner.find_best_trades(limit=limit, deep=deep)
    return _json(report.model_dump())


@mcp.tool()
async def scan_stocks(
    symbols: str = "",
    limit: int = 10,
    min_score: float = 0.0,
    action: str = "any",
) -> str:
    """Score and rank a list of stocks to find which are the strongest trades.
    symbols: comma-separated tickers (blank scans trending names).
    action: 'buy', 'sell' or 'any' to filter direction."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    report = await scanner.scan_stocks(
        symbols=symbol_list, limit=limit, min_score=min_score, action=action
    )
    return _json(report.model_dump())


@mcp.tool()
async def scan_sector(sector: str, limit: int = 8) -> str:
    """Find the best trade setups within a sector.
    Options: tech, ai, finance, healthcare, energy, consumer, crypto."""
    report = await scanner.scan_sector(sector, limit=limit)
    return _json(report.model_dump())


@mcp.tool()
async def scan_market_movers(limit: int = 10) -> str:
    """Get today's biggest gainers, biggest losers (dip candidates) and most active stocks."""
    return _json({
        "gainers": [q.model_dump() for q in await scanner.screener.top_gainers(limit)],
        "losers": [q.model_dump() for q in await scanner.screener.top_losers(limit)],
        "most_active": [q.model_dump() for q in await scanner.screener.most_active(limit)],
    })


@mcp.tool()
async def scan_trending_tickers(limit: int = 15) -> str:
    """Get the tickers with the most market attention right now, with live quotes."""
    symbols = await scanner.screener.trending(limit)
    quotes = await scanner.screener.get_universe_quotes(symbols)
    return _json({"symbols": symbols, "quotes": [q.model_dump() for q in quotes]})


@mcp.tool()
async def scan_insider_buys(days: int = 14, min_insiders: int = 2, limit: int = 10) -> str:
    """Find stocks where multiple company insiders bought shares recently — one of the
    strongest bullish signals available. Data from OpenInsider.com (SEC Form 4)."""
    report = await scanner.scan_insider_buys(
        days=days, min_insiders=min_insiders, limit=limit
    )
    return _json(report.model_dump())


@mcp.tool()
async def scan_insider_buys_market_wide(
    days: int = 7, min_value_usd: int = 100000, limit: int = 40
) -> str:
    """List every notable insider PURCHASE across the whole market in the last N days,
    filtered by minimum dollar value. Data from OpenInsider.com (SEC Form 4)."""
    trades = await trader.researcher.insider.get_market_wide_buys(
        days=days, min_value_usd=min_value_usd, limit=limit
    )
    return _json({
        "trades": [t.model_dump() for t in trades],
        "source": "openinsider.com (SEC Form 4)",
    })


@mcp.tool()
async def scan_prediction_markets(platform: str = "kalshi", limit: int = 10) -> str:
    """Find the best prediction-market contracts to trade on Kalshi or Polymarket:
    high-probability carry trades and wide-spread liquidity opportunities.
    platform: 'kalshi', 'polymarket', or 'both'."""
    report = await scanner.find_prediction_opportunities(platform=platform, limit=limit)
    return _json(report.model_dump())


@mcp.tool()
async def compare_stocks(symbols: str) -> str:
    """Rank several stocks head-to-head to see which is the best trade right now.
    symbols: comma-separated tickers, e.g. 'AAPL,MSFT,NVDA'."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    ranked = await scanner.compare(symbol_list)
    return _json({
        "ranked": [o.model_dump() for o in ranked],
        "winner": ranked[0].symbol if ranked else None,
    })


# ── Live Growth Trading (multi-platform) ───────────────────────────────────────


@mcp.tool()
async def growth_setup(starting_capital: float = 0, targets: str = "2,3") -> str:
    """Initialize live growth trading with your starting capital and targets (2x, 3x).
    YOU fund your own broker accounts — this does not hold your money.
    Example: growth_setup(1000, "2,3") targets $2000 and $3000."""
    capital = starting_capital or None
    target_list = [float(t) for t in targets.split(",") if t.strip()]
    return _json(await growth_trader.setup(capital, target_list))


@mcp.tool()
async def growth_status() -> str:
    """Get growth progress: current value, multiplier, 2x/3x milestone progress, platform balances."""
    return _json(await growth_trader.status())


@mcp.tool()
async def growth_platform_check() -> str:
    """Check which platforms are ready for live trading and what's missing."""
    return _json({
        "readiness": growth_trader.balances.platform_readiness(),
        "live_check": await growth_trader._check_live_ready(),
    })


@mcp.tool()
async def growth_run_live_cycle(force: bool = False) -> str:
    """Run one live multi-platform trading cycle: analyze markets → execute on Robinhood, Kalshi, Polymarket.
  Requires GROWTH_LIVE_ENABLED=true, GROWTH_LIVE_ACK=I_ACCEPT_FINANCIAL_RISK, AI_DRY_RUN=false,
  and platform API credentials configured."""
    return _json(await growth_trader.run_live_cycle(force=force))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
