"""Fetch live balances across all connected platforms."""

from __future__ import annotations

from typing import Any

from market_agent.config import Settings
from market_agent.connectors import KalshiConnector, PolymarketConnector, RobinhoodConnector
from market_agent.intelligence.market_data import MarketDataFetcher
from market_agent.trader.paper_broker import PaperBroker


class PlatformBalances:
    """Aggregate portfolio value from Robinhood, Kalshi, Polymarket, and paper."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.robinhood = RobinhoodConnector(settings.robinhood)
        self.kalshi = KalshiConnector(settings.kalshi)
        self.polymarket = PolymarketConnector(settings.polymarket)
        self.paper = PaperBroker(
            portfolio_path=settings.ai.paper_portfolio_path,
            starting_cash=settings.ai.paper_starting_cash,
        )
        self._market = MarketDataFetcher()

    async def close(self) -> None:
        await self.robinhood.close()
        await self.kalshi.close()
        await self.polymarket.close()
        await self.paper.close()
        await self._market.close()

    async def fetch_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {
            "robinhood": await self._robinhood_value(),
            "kalshi": await self._kalshi_value(),
            "polymarket": await self._polymarket_value(),
            "paper": await self._paper_value(),
        }
        total = sum(p.get("total_usd", 0) for p in results.values() if isinstance(p, dict))
        results["total_usd"] = round(total, 2)
        return results

    async def _robinhood_value(self) -> dict[str, Any]:
        if not self.settings.robinhood.is_authenticated:
            return {"total_usd": 0, "status": "not_authenticated"}
        try:
            portfolio = await self.robinhood.get_portfolio()
            results = portfolio.get("results", [portfolio]) if isinstance(portfolio, dict) else []
            equity = 0.0
            for p in results:
                equity += float(p.get("equity", p.get("extended_hours_equity", 0)) or 0)
            return {"total_usd": round(equity, 2), "status": "ok", "raw": portfolio}
        except Exception as exc:
            return {"total_usd": 0, "status": "error", "error": str(exc)}

    async def _kalshi_value(self) -> dict[str, Any]:
        if not self.settings.kalshi.is_authenticated:
            return {"total_usd": 0, "status": "not_authenticated"}
        try:
            balance = await self.kalshi.get_balance()
            cents = balance.get("balance", 0)
            portfolio_value = balance.get("portfolio_value", 0)
            total_cents = cents + portfolio_value
            return {
                "total_usd": round(total_cents / 100, 2),
                "status": "ok",
                "balance_usd": round(cents / 100, 2),
                "positions_usd": round(portfolio_value / 100, 2),
            }
        except Exception as exc:
            return {"total_usd": 0, "status": "error", "error": str(exc)}

    async def _polymarket_value(self) -> dict[str, Any]:
        if not self.settings.polymarket.wallet_address:
            return {"total_usd": 0, "status": "not_configured"}
        try:
            positions = await self.polymarket.get_positions()
            total = sum(float(p.get("currentValue", p.get("value", 0)) or 0) for p in positions)
            return {"total_usd": round(total, 2), "status": "ok", "position_count": len(positions)}
        except Exception as exc:
            return {"total_usd": 0, "status": "error", "error": str(exc)}

    async def _paper_value(self) -> dict[str, Any]:
        try:
            portfolio = await self.paper.get_portfolio()
            return {"total_usd": portfolio.get("total_value", 0), "status": "ok"}
        except Exception as exc:
            return {"total_usd": 0, "status": "error", "error": str(exc)}

    def platform_readiness(self) -> dict[str, Any]:
        """Check which platforms are ready for live trading."""
        s = self.settings
        return {
            "robinhood": {
                "ready": s.robinhood.is_authenticated,
                "needs": [] if s.robinhood.is_authenticated else ["ROBINHOOD_ACCESS_TOKEN"],
            },
            "kalshi": {
                "ready": s.kalshi.is_authenticated and not s.kalshi.use_demo,
                "needs": (
                    []
                    if s.kalshi.is_authenticated and not s.kalshi.use_demo
                    else ["KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH", "KALSHI_USE_DEMO=false"]
                ),
            },
            "polymarket": {
                "ready": s.polymarket.is_authenticated,
                "needs": (
                    []
                    if s.polymarket.is_authenticated
                    else ["POLYMARKET_CLOB_API_KEY", "POLYMARKET_CLOB_SECRET",
                          "POLYMARKET_CLOB_PASSPHRASE", "POLYMARKET_WALLET_ADDRESS"]
                ),
            },
            "paper": {"ready": True, "needs": []},
        }
