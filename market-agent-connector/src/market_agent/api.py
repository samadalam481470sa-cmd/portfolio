"""REST API wrapper for non-MCP AI agent clients."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from market_agent.ai.opportunity_scanner import OpportunityScanner
from market_agent.config import load_settings
from market_agent.connectors import KalshiConnector, PolymarketConnector, RobinhoodConnector
from market_agent.trader.auto_trader import AutoTrader
from market_agent.growth.growth_trader import GrowthTrader

settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.polymarket = PolymarketConnector(settings.polymarket)
    app.state.kalshi = KalshiConnector(settings.kalshi)
    app.state.robinhood = RobinhoodConnector(settings.robinhood)
    app.state.trader = AutoTrader(settings)
    app.state.growth = GrowthTrader(settings)
    app.state.scanner = OpportunityScanner(
        researcher=app.state.trader.researcher,
        kalshi=app.state.kalshi,
        polymarket=app.state.polymarket,
    )
    yield
    await app.state.scanner.close()
    await app.state.polymarket.close()
    await app.state.kalshi.close()
    await app.state.robinhood.close()
    await app.state.trader.close()
    await app.state.growth.close()


app = FastAPI(
    title="Market Agent Connector API",
    description="REST API for AI agents — Polymarket, Kalshi, Robinhood + AI trading engine",
    version="0.2.0",
    lifespan=lifespan,
)


class KalshiOrderRequest(BaseModel):
    ticker: str
    side: str = Field(description="'yes' or 'no'")
    action: str = Field(description="'buy' or 'sell'")
    count: int
    yes_price: int | None = None
    no_price: int | None = None


class PolymarketOrderRequest(BaseModel):
    token_id: str
    price: float
    size: float
    side: str = Field(description="'BUY' or 'SELL'")


@app.get("/health")
async def health() -> dict[str, Any]:
    pm = app.state.polymarket
    ka = app.state.kalshi
    rh = app.state.robinhood
    return {
        "status": "ok",
        "platforms": {
            "polymarket": await pm.health(),
            "kalshi": await ka.health(),
            "robinhood": await rh.health(),
        },
    }


# ── Polymarket ───────────────────────────────────────────────────────────────


@app.get("/polymarket/search")
async def polymarket_search(q: str = Query(...), limit: int = 10):
    return await app.state.polymarket.search_markets(q, limit)


@app.get("/polymarket/events")
async def polymarket_events(limit: int = 20, active: bool = True, tag: str | None = None):
    return await app.state.polymarket.list_events(limit, active, tag)


@app.get("/polymarket/events/{slug}")
async def polymarket_event(slug: str):
    return await app.state.polymarket.get_event(slug)


@app.get("/polymarket/orderbook/{token_id}")
async def polymarket_orderbook(token_id: str):
    return await app.state.polymarket.get_orderbook(token_id)


@app.get("/polymarket/positions")
async def polymarket_positions(user_address: str | None = None):
    return await app.state.polymarket.get_positions(user_address)


@app.post("/polymarket/orders")
async def polymarket_place_order(req: PolymarketOrderRequest):
    try:
        return await app.state.polymarket.place_limit_order(
            req.token_id, req.price, req.size, req.side
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ── Kalshi ───────────────────────────────────────────────────────────────────


@app.get("/kalshi/events")
async def kalshi_events(limit: int = 20, status: str | None = None):
    return await app.state.kalshi.list_events(limit, status)


@app.get("/kalshi/markets")
async def kalshi_markets(limit: int = 20, status: str = "open", event_ticker: str | None = None):
    return await app.state.kalshi.list_markets(limit, status, event_ticker)


@app.get("/kalshi/markets/{ticker}")
async def kalshi_market(ticker: str):
    return await app.state.kalshi.get_market(ticker)


@app.get("/kalshi/markets/{ticker}/orderbook")
async def kalshi_orderbook(ticker: str, depth: int = 10):
    return await app.state.kalshi.get_orderbook(ticker, depth)


@app.get("/kalshi/balance")
async def kalshi_balance():
    try:
        return await app.state.kalshi.get_balance()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/kalshi/positions")
async def kalshi_positions(ticker: str | None = None):
    try:
        return await app.state.kalshi.get_positions(ticker)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/kalshi/orders")
async def kalshi_place_order(req: KalshiOrderRequest):
    try:
        return await app.state.kalshi.create_order(
            req.ticker, req.side, req.action, req.count, req.yes_price, req.no_price
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ── Robinhood ────────────────────────────────────────────────────────────────


@app.get("/robinhood/auth-url")
async def robinhood_auth_url(state: str = "market-agent"):
    try:
        return {"url": app.state.robinhood.get_authorization_url(state)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/robinhood/account")
async def robinhood_account():
    try:
        return await app.state.robinhood.get_account()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/robinhood/portfolio")
async def robinhood_portfolio():
    try:
        return await app.state.robinhood.get_portfolio()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/robinhood/positions")
async def robinhood_positions():
    try:
        return await app.state.robinhood.get_positions()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ── AI Trading Engine ────────────────────────────────────────────────────────


@app.get("/ai/quote/{symbol}")
async def ai_quote(symbol: str):
    research = await app.state.trader.research(symbol)
    return research.market


@app.get("/ai/news/{symbol}")
async def ai_news(symbol: str, limit: int = 10):
    news = await app.state.trader.researcher.news.get_stock_news(symbol, limit)
    return [n.model_dump() for n in news]


@app.get("/ai/technicals/{symbol}")
async def ai_technicals(symbol: str):
    return await app.state.trader.researcher.market_data.get_technicals(symbol)


@app.get("/ai/research/{symbol}")
async def ai_research(symbol: str):
    research = await app.state.trader.research(symbol)
    return research.model_dump()


@app.get("/ai/analyze/{symbol}")
async def ai_analyze(symbol: str, platform: str = "paper"):
    research, signal = await app.state.trader.analyze(symbol, platform=platform)
    return {"signal": signal.model_dump(), "price": research.market.price if research.market else None}


@app.post("/ai/execute/{symbol}")
async def ai_execute(symbol: str, platform: str = "paper", force: bool = False):
    _, signal = await app.state.trader.analyze(symbol, platform=platform)
    result = await app.state.trader.execute_signal(signal, force=force, platform=platform)
    return result.model_dump()


@app.post("/ai/cycle")
async def ai_cycle(symbols: str = "", platform: str = "paper", force: bool = False):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    report = await app.state.trader.run_cycle(symbols=symbol_list, platform=platform, force=force)
    return report.model_dump()


@app.get("/ai/paper-portfolio")
async def ai_paper_portfolio():
    return await app.state.trader.get_paper_portfolio()


@app.get("/ai/web-search")
async def ai_web_search(q: str = Query(...)):
    snippets = await app.state.trader.researcher.web.research(q)
    return {"query": q, "snippets": snippets}


@app.get("/ai/insider/{symbol}")
async def ai_insider(symbol: str, days: int = 180):
    summary = await app.state.trader.researcher.insider.get_summary(symbol, days=days)
    trades = await app.state.trader.researcher.insider.get_trades(symbol, limit=20, days=days)
    return {
        "summary": summary.model_dump(),
        "trades": [t.model_dump() for t in trades],
        "source": "openinsider.com (SEC Form 4)",
    }


@app.get("/ai/predict/{symbol}")
async def ai_predict(symbol: str):
    from market_agent.ai.market_predictor import MarketPredictor
    research = await app.state.trader.research(symbol)
    prediction = await MarketPredictor().predict(research)
    return prediction.model_dump()


@app.get("/ai/signals")
async def ai_signals():
    if not hasattr(app.state, "auto_executor"):
        from market_agent.trader.auto_executor import AutoExecutor
        app.state.auto_executor = AutoExecutor(app.state.trader, settings)
    return await app.state.auto_executor.get_signals()


@app.post("/ai/auto/start")
async def ai_auto_start(platform: str = "paper", interval_min: int = 15, force: bool = False):
    if not hasattr(app.state, "auto_executor"):
        from market_agent.trader.auto_executor import AutoExecutor
        app.state.auto_executor = AutoExecutor(app.state.trader, settings)
    return await app.state.auto_executor.start(platform=platform, interval_min=interval_min, force=force)


@app.post("/ai/auto/stop")
async def ai_auto_stop():
    if not hasattr(app.state, "auto_executor"):
        from market_agent.trader.auto_executor import AutoExecutor
        app.state.auto_executor = AutoExecutor(app.state.trader, settings)
    return await app.state.auto_executor.stop()


@app.get("/ai/auto/status")
async def ai_auto_status():
    if not hasattr(app.state, "auto_executor"):
        from market_agent.trader.auto_executor import AutoExecutor
        app.state.auto_executor = AutoExecutor(app.state.trader, settings)
    return app.state.auto_executor.status()


# ── Opportunity Discovery ────────────────────────────────────────────────────


@app.get("/scan/best")
async def scan_best(limit: int = 10, deep: bool = False):
    """Scan movers, trending names and insider clusters, ranked by conviction."""
    report = await app.state.scanner.find_best_trades(limit=limit, deep=deep)
    return report.model_dump()


@app.get("/scan/stocks")
async def scan_stocks(
    symbols: str = "",
    limit: int = 10,
    min_score: float = 0.0,
    action: str = "any",
    include_news: bool = False,
):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    report = await app.state.scanner.scan_stocks(
        symbols=symbol_list,
        limit=limit,
        min_score=min_score,
        action=action,
        include_news=include_news,
    )
    return report.model_dump()


@app.get("/scan/sector/{sector}")
async def scan_sector(sector: str, limit: int = 8):
    report = await app.state.scanner.scan_sector(sector, limit=limit)
    return report.model_dump()


@app.get("/scan/movers")
async def scan_movers(limit: int = 10):
    screener = app.state.scanner.screener
    return {
        "gainers": [q.model_dump() for q in await screener.top_gainers(limit)],
        "losers": [q.model_dump() for q in await screener.top_losers(limit)],
        "most_active": [q.model_dump() for q in await screener.most_active(limit)],
    }


@app.get("/scan/trending")
async def scan_trending(limit: int = 15):
    symbols = await app.state.scanner.screener.trending(limit)
    quotes = await app.state.scanner.screener.get_universe_quotes(symbols)
    return {"symbols": symbols, "quotes": [q.model_dump() for q in quotes]}


@app.get("/scan/insider-buys")
async def scan_insider_buys(days: int = 14, min_insiders: int = 2, limit: int = 10):
    report = await app.state.scanner.scan_insider_buys(
        days=days, min_insiders=min_insiders, limit=limit
    )
    return report.model_dump()


@app.get("/scan/insider-market-wide")
async def scan_insider_market_wide(days: int = 7, min_value_usd: int = 100_000, limit: int = 40):
    trades = await app.state.trader.researcher.insider.get_market_wide_buys(
        days=days, min_value_usd=min_value_usd, limit=limit
    )
    return {
        "trades": [t.model_dump() for t in trades],
        "source": "openinsider.com (SEC Form 4)",
    }


@app.get("/scan/predictions")
async def scan_predictions(platform: str = "kalshi", limit: int = 10):
    report = await app.state.scanner.find_prediction_opportunities(
        platform=platform, limit=limit
    )
    return report.model_dump()


@app.get("/scan/compare")
async def scan_compare(symbols: str = Query(..., description="Comma-separated tickers")):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if len(symbol_list) < 2:
        raise HTTPException(400, "Provide at least two symbols")
    ranked = await app.state.scanner.compare(symbol_list)
    return {
        "ranked": [o.model_dump() for o in ranked],
        "winner": ranked[0].symbol if ranked else None,
    }


# ── Live Growth Trading ──────────────────────────────────────────────────────


@app.post("/growth/setup")
async def growth_setup(starting_capital: float = 1000, targets: str = "2,3"):
    target_list = [float(t) for t in targets.split(",") if t.strip()]
    return await app.state.growth.setup(starting_capital, target_list)


@app.get("/growth/status")
async def growth_status():
    return await app.state.growth.status()


@app.get("/growth/platform-check")
async def growth_platform_check():
    return {
        "readiness": app.state.growth.balances.platform_readiness(),
        "live_check": await app.state.growth._check_live_ready(),
    }


@app.post("/growth/run-cycle")
async def growth_run_cycle(force: bool = False):
    return await app.state.growth.run_live_cycle(force=force)


def main() -> None:
    uvicorn.run(
        "market_agent.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
