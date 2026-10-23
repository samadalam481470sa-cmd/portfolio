"""Auto-trader orchestrator — research → AI decision → risk check → execute."""

from __future__ import annotations

from typing import Any

from market_agent.ai.decision_engine import DecisionEngine
from market_agent.ai.llm_client import LLMClient
from market_agent.ai.models import (
    ResearchBundle,
    TradeAction,
    TradeExecutionResult,
    TradeSignal,
    TradingCycleReport,
)
from market_agent.ai.risk_manager import RiskManager
from market_agent.config import AISettings, Settings
from market_agent.connectors import KalshiConnector, PolymarketConnector, RobinhoodConnector
from market_agent.intelligence.researcher import IntelligenceResearcher
from market_agent.trader.paper_broker import PaperBroker


class AutoTrader:
    """End-to-end AI trading pipeline."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        ai = self.settings.ai

        llm = LLMClient(ai.api_key, ai.model, ai.base_url) if ai.api_key else None
        self.researcher = IntelligenceResearcher(finnhub_api_key=ai.finnhub_api_key)
        self.engine = DecisionEngine(llm)
        self.llm = llm
        self.risk = RiskManager(
            max_position_usd=ai.max_position_usd,
            max_single_trade_usd=ai.max_single_trade_usd,
            min_confidence=ai.min_confidence,
            require_confirmation=ai.require_confirmation,
            dry_run=ai.dry_run,
            allowed_symbols=ai.symbols() or None,
        )
        self.paper = PaperBroker(
            portfolio_path=ai.paper_portfolio_path,
            starting_cash=ai.paper_starting_cash,
        )
        self.robinhood = RobinhoodConnector(self.settings.robinhood)
        self.kalshi = KalshiConnector(self.settings.kalshi)
        self.polymarket = PolymarketConnector(self.settings.polymarket)

    async def close(self) -> None:
        await self.researcher.close()
        if self.llm:
            await self.llm.close()
        await self.paper.close()
        await self.robinhood.close()
        await self.kalshi.close()
        await self.polymarket.close()

    async def research(self, symbol: str) -> ResearchBundle:
        return await self.researcher.research_stock(symbol)

    async def analyze(self, symbol: str, platform: str = "paper") -> tuple[ResearchBundle, TradeSignal]:
        research = await self.research(symbol)
        signal = await self.engine.analyze(research, platform=platform)
        price = research.market.price if research.market else None
        if price and signal.quantity > 0:
            signal.quantity = self.risk.cap_quantity(signal.quantity, price)
        return research, signal

    async def execute_signal(
        self,
        signal: TradeSignal,
        force: bool = False,
        platform: str | None = None,
    ) -> TradeExecutionResult:
        platform = platform or signal.platform or "paper"
        price = signal.limit_price

        valid, reason = self.risk.validate_signal(signal, price)
        if not valid:
            return TradeExecutionResult(
                signal=signal,
                executed=False,
                dry_run=self.risk.dry_run,
                platform=platform,
                message=f"Risk check failed: {reason}",
            )

        if not self.risk.should_execute(signal, force=force):
            return TradeExecutionResult(
                signal=signal,
                executed=False,
                dry_run=True,
                platform=platform,
                message=(
                    f"Dry-run / confirmation required. Signal: {signal.action.value} "
                    f"{signal.quantity} {signal.symbol} (confidence {signal.confidence:.0%}). "
                    f"Set AI_DRY_RUN=false and AI_REQUIRE_CONFIRMATION=false, or pass force=true."
                ),
            )

        if platform == "paper":
            return await self.paper.execute(signal)

        if platform == "robinhood":
            return await self._execute_robinhood(signal)

        if platform == "kalshi":
            return await self._execute_kalshi(signal)

        if platform == "polymarket":
            return await self._execute_polymarket(signal)

        return TradeExecutionResult(
            signal=signal,
            executed=False,
            dry_run=False,
            platform=platform,
            message=f"Unknown platform: {platform}",
        )

    async def run_cycle(
        self,
        symbols: list[str] | None = None,
        platform: str = "paper",
        force: bool = False,
    ) -> TradingCycleReport:
        """Full pipeline: research all symbols → analyze → execute approved trades."""
        watchlist = symbols or self.settings.ai.symbols() or ["AAPL", "MSFT", "GOOGL"]
        all_research: list[ResearchBundle] = []
        all_signals: list[TradeSignal] = []
        all_executions: list[TradeExecutionResult] = []

        for symbol in watchlist:
            research, signal = await self.analyze(symbol, platform=platform)
            all_research.append(research)
            all_signals.append(signal)
            if signal.action != TradeAction.HOLD:
                result = await self.execute_signal(signal, force=force, platform=platform)
                all_executions.append(result)

        buys = sum(1 for s in all_signals if s.action == TradeAction.BUY)
        sells = sum(1 for s in all_signals if s.action == TradeAction.SELL)
        holds = sum(1 for s in all_signals if s.action == TradeAction.HOLD)
        executed = sum(1 for e in all_executions if e.executed)

        summary = (
            f"Analyzed {len(watchlist)} symbols: {buys} buy, {sells} sell, {holds} hold. "
            f"Executed {executed} trades on {platform}."
        )

        return TradingCycleReport(
            symbols_analyzed=watchlist,
            signals=all_signals,
            executions=all_executions,
            research=all_research,
            summary=summary,
        )

    async def get_paper_portfolio(self) -> dict[str, Any]:
        return await self.paper.get_portfolio()

    async def _execute_robinhood(self, signal: TradeSignal) -> TradeExecutionResult:
        try:
            result = await self.robinhood.place_order(
                symbol=signal.symbol,
                side=signal.action.value,
                quantity=signal.quantity,
                order_type="market",
            )
            return TradeExecutionResult(
                signal=signal,
                executed=True,
                dry_run=False,
                platform="robinhood",
                order_id=result.get("id"),
                message=f"Robinhood {signal.action.value}: {signal.quantity} {signal.symbol}",
                details=result,
            )
        except Exception as exc:
            return TradeExecutionResult(
                signal=signal,
                executed=False,
                dry_run=False,
                platform="robinhood",
                message=str(exc),
            )

    async def _execute_kalshi(self, signal: TradeSignal) -> TradeExecutionResult:
        ticker = signal.metadata.get("kalshi_ticker", signal.symbol)
        try:
            result = await self.kalshi.create_order(
                ticker=ticker,
                side=signal.metadata.get("side", "yes"),
                action=signal.action.value,
                count=signal.quantity,
                yes_price=int(signal.limit_price * 100) if signal.limit_price else None,
            )
            return TradeExecutionResult(
                signal=signal,
                executed=True,
                dry_run=False,
                platform="kalshi",
                order_id=result.get("order", {}).get("order_id"),
                message=f"Kalshi {signal.action.value}: {signal.quantity} on {ticker}",
                details=result,
            )
        except Exception as exc:
            return TradeExecutionResult(
                signal=signal,
                executed=False,
                dry_run=False,
                platform="kalshi",
                message=str(exc),
            )

    async def _execute_polymarket(self, signal: TradeSignal) -> TradeExecutionResult:
        token_id = signal.metadata.get("token_id", signal.symbol)
        try:
            result = await self.polymarket.place_limit_order(
                token_id=token_id,
                price=signal.limit_price or 0.5,
                size=float(signal.quantity),
                side=signal.action.value.upper(),
            )
            return TradeExecutionResult(
                signal=signal,
                executed=True,
                dry_run=False,
                platform="polymarket",
                order_id=result.get("orderID"),
                message=f"Polymarket {signal.action.value}: {signal.quantity} @ {signal.limit_price}",
                details=result,
            )
        except Exception as exc:
            return TradeExecutionResult(
                signal=signal,
                executed=False,
                dry_run=False,
                platform="polymarket",
                message=str(exc),
            )
