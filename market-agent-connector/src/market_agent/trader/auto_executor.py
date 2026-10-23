"""Automatic buy/sell executor — monitors watchlist and trades on AI signals."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

from market_agent.ai.market_predictor import MarketPredictor
from market_agent.ai.models import TradeAction
from market_agent.config import Settings
from market_agent.trader.auto_trader import AutoTrader

logger = logging.getLogger(__name__)

OnTradeCallback = Callable[[str], Awaitable[None]]


class AutoExecutor:
    """Watches symbols and automatically executes buy/sell when AI signals trigger."""

    def __init__(
        self,
        trader: AutoTrader,
        settings: Settings,
        state_path: str = "auto_executor.json",
    ) -> None:
        self.trader = trader
        self.settings = settings
        self.predictor = MarketPredictor()
        self.state_path = Path(state_path)
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_trade: OnTradeCallback | None = None
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {
            "active": False,
            "platform": "paper",
            "symbols": [],
            "interval_min": 15,
            "last_run": None,
            "trades_executed": 0,
            "history": [],
        }

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self._state, indent=2, default=str))

    @property
    def is_running(self) -> bool:
        return self._running

    def set_notify_callback(self, callback: OnTradeCallback) -> None:
        self._on_trade = callback

    async def start(
        self,
        symbols: list[str] | None = None,
        platform: str = "paper",
        interval_min: int = 15,
        force: bool = False,
    ) -> dict[str, Any]:
        if self._running:
            return {"status": "already_running", "state": self._state}

        syms = symbols or self.settings.ai.symbols()
        self._state.update({
            "active": True,
            "platform": platform,
            "symbols": syms,
            "interval_min": interval_min,
            "force": force,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save_state()
        self._running = True
        self._task = asyncio.create_task(self._loop(interval_min, platform, force))
        return {
            "status": "started",
            "symbols": syms,
            "platform": platform,
            "interval_min": interval_min,
            "message": f"Auto-trading {len(syms)} symbols every {interval_min}min on {platform}",
        }

    async def stop(self) -> dict[str, Any]:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._state["active"] = False
        self._save_state()
        return {
            "status": "stopped",
            "trades_executed": self._state["trades_executed"],
            "message": "Auto-trading stopped",
        }

    async def run_once(self, platform: str = "paper", force: bool = False) -> dict[str, Any]:
        """Run a single scan + execute cycle immediately."""
        symbols = self._state.get("symbols") or self.settings.ai.symbols()
        return await self._execute_cycle(symbols, platform, force)

    async def get_signals(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        """Get current buy/sell/hold signals for all watchlist symbols."""
        syms = symbols or self.settings.ai.symbols()
        results = []
        for symbol in syms:
            try:
                research = await self.trader.research(symbol)
                prediction = await self.predictor.predict(research)
                _, signal = await self.trader.analyze(symbol, platform="paper")
                results.append({
                    "symbol": symbol,
                    "action": signal.action.value,
                    "confidence": signal.confidence,
                    "prediction": prediction.model_dump(),
                    "reasoning": signal.reasoning[:200],
                })
            except Exception as exc:
                results.append({"symbol": symbol, "error": str(exc)})
        return results

    async def _loop(self, interval_min: int, platform: str, force: bool) -> None:
        while self._running:
            try:
                symbols = self._state.get("symbols") or self.settings.ai.symbols()
                result = await self._execute_cycle(symbols, platform, force)
                self._state["last_run"] = datetime.now(timezone.utc).isoformat()
                self._save_state()
                if self._on_trade and result.get("executions"):
                    msg = self._format_cycle_message(result)
                    await self._on_trade(msg)
            except Exception as exc:
                logger.exception("Auto-executor cycle error: %s", exc)
                if self._on_trade:
                    await self._on_trade(f"⚠️ Auto-trader error: {exc}")

            await asyncio.sleep(interval_min * 60)

    async def _execute_cycle(
        self, symbols: list[str], platform: str, force: bool
    ) -> dict[str, Any]:
        executions = []
        signals = []

        # Get current positions for sell decisions
        positions = await self._get_positions(platform)

        for symbol in symbols:
            try:
                research = await self.trader.research(symbol)
                prediction = await self.predictor.predict(research)
                _, signal = await self.trader.analyze(symbol, platform=platform)

                # Override with prediction if stronger
                if prediction.confidence > signal.confidence:
                    signal.action = prediction.recommended_action
                    signal.confidence = prediction.confidence
                    signal.reasoning = prediction.summary

                has_position = symbol in positions and positions[symbol] > 0

                # Smart execution rules
                should_trade = False
                if signal.action == TradeAction.BUY and not has_position:
                    should_trade = signal.confidence >= self.settings.ai.min_confidence
                elif signal.action == TradeAction.SELL and has_position:
                    should_trade = signal.confidence >= self.settings.ai.min_confidence
                elif signal.action == TradeAction.SELL and not has_position:
                    signal.action = TradeAction.HOLD  # can't sell what we don't have

                signals.append({
                    "symbol": symbol,
                    "action": signal.action.value,
                    "confidence": signal.confidence,
                    "prediction_direction": prediction.direction,
                    "price_target": prediction.price_target_1d,
                    "should_trade": should_trade,
                })

                if should_trade:
                    price = research.market.price if research.market else signal.limit_price
                    if price and signal.quantity <= 0:
                        signal.quantity = self.trader.risk.cap_quantity(
                            max(1, int(200 / price)), price
                        )
                    if signal.action == TradeAction.SELL and has_position:
                        signal.quantity = min(signal.quantity, positions[symbol])

                    result = await self.trader.execute_signal(signal, force=force, platform=platform)
                    executions.append(result.model_dump())

                    if result.executed:
                        self._state["trades_executed"] += 1
                        self._state["history"].append({
                            "symbol": symbol,
                            "action": signal.action.value,
                            "quantity": signal.quantity,
                            "platform": platform,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        if len(self._state["history"]) > 100:
                            self._state["history"] = self._state["history"][-100:]
                        self._save_state()

            except Exception as exc:
                signals.append({"symbol": symbol, "error": str(exc)})

        executed = sum(1 for e in executions if e.get("executed"))
        return {
            "signals": signals,
            "executions": executions,
            "executed_count": executed,
            "summary": f"Scanned {len(symbols)} symbols, executed {executed} trades",
        }

    async def _get_positions(self, platform: str) -> dict[str, int]:
        positions: dict[str, int] = {}
        if platform == "paper":
            pf = await self.trader.get_paper_portfolio()
            for sym, pos in pf.get("positions", {}).items():
                positions[sym] = pos.get("quantity", 0)
        return positions

    def _format_cycle_message(self, result: dict[str, Any]) -> str:
        lines = [f"🤖 *Auto-Trader Cycle*\n", result.get("summary", "")]
        for sig in result.get("signals", []):
            if sig.get("should_trade") or sig.get("action") != "hold":
                emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(sig.get("action", ""), "⚪")
                lines.append(
                    f"{emoji} {sig.get('action', '').upper()} `{sig.get('symbol')}` "
                    f"({sig.get('confidence', 0):.0%}) → target ${sig.get('price_target', '?')}"
                )
        for ex in result.get("executions", []):
            if ex.get("executed"):
                lines.append(f"✅ {ex.get('message', 'Trade executed')}")
        return "\n".join(lines)

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            **self._state,
        }
