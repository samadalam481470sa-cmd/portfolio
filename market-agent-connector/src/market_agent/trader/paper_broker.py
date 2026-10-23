"""Paper trading broker — simulates stock trades using live Yahoo prices."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_agent.ai.models import TradeAction, TradeExecutionResult, TradeSignal
from market_agent.intelligence.market_data import MarketDataFetcher


class PaperBroker:
    """Simulated brokerage account persisted to a local JSON file."""

    def __init__(self, portfolio_path: str = "paper_portfolio.json", starting_cash: float = 10000.0) -> None:
        self.portfolio_path = Path(portfolio_path)
        self.starting_cash = starting_cash
        self._market = MarketDataFetcher()
        self._portfolio = self._load()

    async def close(self) -> None:
        await self._market.close()

    def _load(self) -> dict[str, Any]:
        if self.portfolio_path.exists():
            return json.loads(self.portfolio_path.read_text())
        return {
            "cash": self.starting_cash,
            "positions": {},
            "orders": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save(self) -> None:
        self.portfolio_path.write_text(json.dumps(self._portfolio, indent=2, default=str))

    async def get_portfolio(self) -> dict[str, Any]:
        positions_value = 0.0
        enriched_positions = {}
        for symbol, pos in self._portfolio["positions"].items():
            try:
                quote = await self._market.get_quote(symbol)
                price = quote.price or pos["avg_cost"]
                value = pos["quantity"] * price
                positions_value += value
                enriched_positions[symbol] = {
                    **pos,
                    "current_price": price,
                    "market_value": round(value, 2),
                    "pnl": round((price - pos["avg_cost"]) * pos["quantity"], 2),
                }
            except Exception:
                enriched_positions[symbol] = pos

        return {
            "cash": self._portfolio["cash"],
            "positions": enriched_positions,
            "total_value": round(self._portfolio["cash"] + positions_value, 2),
            "order_count": len(self._portfolio["orders"]),
        }

    async def execute(self, signal: TradeSignal) -> TradeExecutionResult:
        if signal.action == TradeAction.HOLD:
            return TradeExecutionResult(
                signal=signal,
                executed=False,
                dry_run=False,
                platform="paper",
                message="HOLD signal — no action taken",
            )

        quote = await self._market.get_quote(signal.symbol)
        price = signal.limit_price or quote.price
        if not price:
            return TradeExecutionResult(
                signal=signal,
                executed=False,
                dry_run=False,
                platform="paper",
                message=f"Cannot get price for {signal.symbol}",
            )

        qty = signal.quantity
        symbol = signal.symbol.upper()
        order_id = f"paper-{len(self._portfolio['orders']) + 1}"

        if signal.action == TradeAction.BUY:
            cost = qty * price
            if cost > self._portfolio["cash"]:
                qty = int(self._portfolio["cash"] / price)
                cost = qty * price
            if qty <= 0:
                return TradeExecutionResult(
                    signal=signal,
                    executed=False,
                    dry_run=False,
                    platform="paper",
                    message="Insufficient cash for buy order",
                )

            pos = self._portfolio["positions"].get(symbol, {"quantity": 0, "avg_cost": 0.0})
            total_qty = pos["quantity"] + qty
            pos["avg_cost"] = ((pos["avg_cost"] * pos["quantity"]) + cost) / total_qty
            pos["quantity"] = total_qty
            self._portfolio["positions"][symbol] = pos
            self._portfolio["cash"] -= cost

        elif signal.action == TradeAction.SELL:
            pos = self._portfolio["positions"].get(symbol)
            if not pos or pos["quantity"] <= 0:
                return TradeExecutionResult(
                    signal=signal,
                    executed=False,
                    dry_run=False,
                    platform="paper",
                    message=f"No position in {symbol} to sell",
                )
            qty = min(qty, pos["quantity"])
            proceeds = qty * price
            pos["quantity"] -= qty
            if pos["quantity"] <= 0:
                del self._portfolio["positions"][symbol]
            self._portfolio["cash"] += proceeds

        order = {
            "id": order_id,
            "symbol": symbol,
            "action": signal.action.value,
            "quantity": qty,
            "price": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reasoning": signal.reasoning[:200],
        }
        self._portfolio["orders"].append(order)
        self._save()

        return TradeExecutionResult(
            signal=signal,
            executed=True,
            dry_run=False,
            platform="paper",
            order_id=order_id,
            message=f"Paper {signal.action.value}: {qty} {symbol} @ ${price:.2f}",
            details=order,
        )
