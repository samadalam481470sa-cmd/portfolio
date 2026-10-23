"""Multi-platform live growth trader — targets 2x/3x capital growth via AI analysis."""

from __future__ import annotations

from typing import Any

from market_agent.ai.models import TradeAction, TradeSignal
from market_agent.config import GrowthSettings, Settings, load_settings
from market_agent.growth.capital_tracker import CapitalTracker
from market_agent.growth.platform_balances import PlatformBalances
from market_agent.growth.position_sizer import PositionSizer
from market_agent.trader.auto_trader import AutoTrader

LIVE_ACK_PHRASE = "I_ACCEPT_FINANCIAL_RISK"


class GrowthTrader:
    """Orchestrates live multi-platform trading toward capital growth targets.

    IMPORTANT: You fund your own broker accounts via API keys. This system does
    NOT hold your money. Growth targets (2x, 3x) are goals, not guarantees.
    Trading involves substantial risk of loss.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.growth = self.settings.growth
        self.trader = AutoTrader(self.settings)
        self.tracker = CapitalTracker(self.growth.state_path)
        self.balances = PlatformBalances(self.settings)
        self.sizer = PositionSizer(
            risk_per_trade_pct=self.growth.risk_per_trade_pct,
            max_position_pct=self.growth.max_position_pct,
        )

    async def close(self) -> None:
        await self.trader.close()
        await self.balances.close()

    def _live_enabled(self) -> tuple[bool, str]:
        if not self.growth.live_enabled:
            return False, "Set GROWTH_LIVE_ENABLED=true to enable live trading"
        if self.growth.live_ack != LIVE_ACK_PHRASE:
            return False, f"Set GROWTH_LIVE_ACK={LIVE_ACK_PHRASE} to confirm you accept financial risk"
        if self.trader.risk.dry_run:
            return False, "Set AI_DRY_RUN=false for live order execution"
        return True, "Live trading enabled"

    async def setup(
        self,
        starting_capital: float | None = None,
        targets: list[float] | None = None,
    ) -> dict[str, Any]:
        """Initialize growth tracking with your starting capital and targets."""
        capital = starting_capital or self.growth.starting_capital
        if capital <= 0:
            raise ValueError("starting_capital must be > 0 (set GROWTH_STARTING_CAPITAL)")

        target_list = targets or self.growth.target_multipliers()
        status = self.tracker.initialize(capital, target_list)
        readiness = self.balances.platform_readiness()

        return {
            "initialized": True,
            "growth_status": status,
            "platform_readiness": readiness,
            "live_ready": await self._check_live_ready(),
            "disclaimer": (
                "You trade with YOUR money in YOUR broker accounts. "
                "2x/3x targets are goals, not guarantees. You can lose your entire investment."
            ),
        }

    async def status(self) -> dict[str, Any]:
        """Full growth + platform status."""
        platform_values = await self.balances.fetch_all()
        total = platform_values.get("total_usd", 0)

        if self.tracker.is_initialized:
            growth = self.tracker.update_value(total)
        else:
            growth = self.tracker.status()

        live_ok, live_msg = self._live_enabled()
        return {
            "growth": growth,
            "platforms": platform_values,
            "readiness": self.balances.platform_readiness(),
            "live_trading": {"enabled": live_ok, "message": live_msg},
            "settings": {
                "targets": self.growth.target_multipliers(),
                "allocations": self.growth.allocations(),
                "cycle_interval_min": self.growth.cycle_interval_min,
            },
        }

    async def _check_live_ready(self) -> dict[str, Any]:
        live_ok, msg = self._live_enabled()
        readiness = self.balances.platform_readiness()
        ready_platforms = [p for p, r in readiness.items() if r["ready"] and p != "paper"]
        return {
            "live_enabled": live_ok,
            "message": msg,
            "ready_platforms": ready_platforms,
            "all_ready": len(ready_platforms) >= 1,
        }

    async def run_live_cycle(self, force: bool = False) -> dict[str, Any]:
        """Execute one full multi-platform live trading cycle."""
        if not self.tracker.is_initialized:
            init = await self.setup()
            if not init:
                return {"error": "Call growth_setup first with starting_capital"}

        live_ok, live_msg = self._live_enabled()
        if not live_ok and not force:
            return {"error": live_msg, "hint": "Use force=true only after configuring live credentials"}

        # Risk halt checks
        if self.tracker.drawdown_pct() >= self.growth.max_drawdown_pct:
            return {
                "halted": True,
                "reason": f"Max drawdown {self.growth.max_drawdown_pct}% exceeded",
                "status": await self.status(),
            }

        daily_pnl = self.tracker.get_daily_pnl()
        if self.tracker.is_initialized:
            daily_loss_pct = abs(daily_pnl / self.tracker.starting_capital * 100)
            if daily_pnl < 0 and daily_loss_pct >= self.growth.max_daily_loss_pct:
                return {
                    "halted": True,
                    "reason": f"Daily loss limit {self.growth.max_daily_loss_pct}% hit",
                    "status": await self.status(),
                }

        platform_values = await self.balances.fetch_all()
        total_capital = platform_values.get("total_usd", self.tracker._data["current_value"])
        multiplier = self.tracker._data.get("multiplier", 1.0)
        allocations = self.growth.allocations()
        all_executions = []
        all_signals = []

        # ── Robinhood stocks ─────────────────────────────────────────────
        if allocations.get("robinhood", 0) > 0 and self.settings.robinhood.is_authenticated:
            budget = self.sizer.platform_budget(total_capital, allocations["robinhood"])
            stock_results = await self._trade_stocks(budget, multiplier, "robinhood", force)
            all_executions.extend(stock_results["executions"])
            all_signals.extend(stock_results["signals"])

        # ── Kalshi prediction markets ──────────────────────────────────
        if allocations.get("kalshi", 0) > 0 and self.settings.kalshi.is_authenticated:
            budget = self.sizer.platform_budget(total_capital, allocations["kalshi"])
            kalshi_results = await self._trade_kalshi(budget, multiplier, force)
            all_executions.extend(kalshi_results["executions"])
            all_signals.extend(kalshi_results["signals"])

        # ── Polymarket ─────────────────────────────────────────────────
        if allocations.get("polymarket", 0) > 0 and self.settings.polymarket.is_authenticated:
            budget = self.sizer.platform_budget(total_capital, allocations["polymarket"])
            poly_results = await self._trade_polymarket(budget, multiplier, force)
            all_executions.extend(poly_results["executions"])
            all_signals.extend(poly_results["signals"])

        # Update tracker
        updated_values = await self.balances.fetch_all()
        growth = self.tracker.update_value(updated_values.get("total_usd", total_capital))

        executed = sum(1 for e in all_executions if e.get("executed"))
        return {
            "cycle_complete": True,
            "executed_trades": executed,
            "total_signals": len(all_signals),
            "growth": growth,
            "executions": all_executions,
            "signals": all_signals,
            "summary": (
                f"Live cycle: {executed}/{len(all_signals)} trades executed. "
                f"Portfolio ${growth['current_value']:.2f} "
                f"({growth['multiplier']:.2f}x, {growth['total_pnl_pct']:+.1f}%). "
                f"Milestones: {growth['milestones_hit'] or 'none yet'}"
            ),
        }

    async def _trade_stocks(
        self, budget: float, multiplier: float, platform: str, force: bool
    ) -> dict[str, Any]:
        symbols = self.settings.ai.symbols()
        executions = []
        signals = []

        for symbol in symbols:
            research, signal = await self.trader.analyze(symbol, platform=platform)
            price = research.market.price if research.market else signal.limit_price
            if signal.action == TradeAction.BUY and price:
                signal.quantity = self.sizer.size_stock_order(
                    budget, price, signal.confidence, multiplier
                )
            elif signal.action == TradeAction.SELL:
                pass  # sell existing positions at analyzed quantity
            else:
                continue

            if signal.quantity <= 0:
                continue

            signals.append(signal.model_dump())
            result = await self.trader.execute_signal(signal, force=force or True, platform=platform)
            executions.append(result.model_dump())
            if result.executed:
                self.tracker.record_trade({
                    "platform": platform, "symbol": symbol,
                    "action": signal.action.value, "quantity": signal.quantity,
                    "price": price, "confidence": signal.confidence,
                })

        return {"executions": executions, "signals": signals}

    async def _trade_kalshi(self, budget: float, multiplier: float, force: bool) -> dict[str, Any]:
        executions = []
        signals = []

        try:
            markets = await self.trader.kalshi.list_markets(limit=10, status="open")
        except Exception as exc:
            return {"executions": [], "signals": [], "error": str(exc)}

        for market in markets.get("markets", [])[:5]:
            ticker = market.get("ticker", "")
            if not ticker:
                continue

            title = market.get("title", ticker)
            research = await self.trader.researcher.research_topic(title)
            signal = await self.trader.engine.analyze(research, platform="kalshi")
            signal.symbol = ticker
            signal.metadata["kalshi_ticker"] = ticker
            signal.metadata["side"] = "yes"

            yes_price = market.get("yes_ask") or market.get("last_price")
            if signal.action == TradeAction.BUY and yes_price:
                signal.quantity = self.sizer.size_contract_order(
                    budget, float(yes_price), signal.confidence, multiplier
                )
                signal.limit_price = float(yes_price) / 100 if yes_price > 1 else float(yes_price)
            elif signal.action != TradeAction.SELL:
                continue

            if signal.quantity <= 0:
                continue

            signals.append(signal.model_dump())
            result = await self.trader.execute_signal(signal, force=force or True, platform="kalshi")
            executions.append(result.model_dump())
            if result.executed:
                self.tracker.record_trade({
                    "platform": "kalshi", "ticker": ticker,
                    "action": signal.action.value, "quantity": signal.quantity,
                })

        return {"executions": executions, "signals": signals}

    async def _trade_polymarket(self, budget: float, multiplier: float, force: bool) -> dict[str, Any]:
        executions = []
        signals = []

        try:
            events = await self.trader.polymarket.list_events(limit=5, active=True)
        except Exception as exc:
            return {"executions": [], "signals": [], "error": str(exc)}

        event_list = events if isinstance(events, list) else events.get("data", events)
        for event in (event_list or [])[:3]:
            title = event.get("title", "")
            markets = event.get("markets", [])
            if not markets:
                continue

            market = markets[0]
            token_ids = market.get("clobTokenIds", [])
            if isinstance(token_ids, str):
                import json
                token_ids = json.loads(token_ids)
            if not token_ids:
                continue

            token_id = token_ids[0]
            research = await self.trader.researcher.research_topic(title)
            signal = await self.trader.engine.analyze(research, platform="polymarket")
            signal.symbol = token_id
            signal.metadata["token_id"] = token_id

            try:
                price_data = await self.trader.polymarket.get_price(token_id, "buy")
                price = float(price_data.get("price", 0.5))
            except Exception:
                price = 0.5

            if signal.action == TradeAction.BUY:
                signal.quantity = self.sizer.size_contract_order(budget, price, signal.confidence, multiplier)
                signal.limit_price = price
            elif signal.action != TradeAction.SELL:
                continue

            if signal.quantity <= 0:
                continue

            signals.append(signal.model_dump())
            result = await self.trader.execute_signal(signal, force=force or True, platform="polymarket")
            executions.append(result.model_dump())
            if result.executed:
                self.tracker.record_trade({
                    "platform": "polymarket", "token_id": token_id,
                    "action": signal.action.value, "quantity": signal.quantity,
                })

        return {"executions": executions, "signals": signals}
