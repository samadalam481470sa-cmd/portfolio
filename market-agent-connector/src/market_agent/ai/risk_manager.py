"""Risk controls for automated trading."""

from __future__ import annotations

from market_agent.ai.models import TradeAction, TradeSignal


class RiskManager:
    def __init__(
        self,
        max_position_usd: float = 1000.0,
        max_single_trade_usd: float = 500.0,
        min_confidence: float = 0.65,
        require_confirmation: bool = True,
        dry_run: bool = True,
        allowed_symbols: list[str] | None = None,
    ) -> None:
        self.max_position_usd = max_position_usd
        self.max_single_trade_usd = max_single_trade_usd
        self.min_confidence = min_confidence
        self.require_confirmation = require_confirmation
        self.dry_run = dry_run
        self.allowed_symbols = {s.upper() for s in allowed_symbols} if allowed_symbols else None

    def validate_signal(self, signal: TradeSignal, current_price: float | None = None) -> tuple[bool, str]:
        if signal.action == TradeAction.HOLD:
            return False, "Signal is HOLD — no trade needed"

        if signal.confidence < self.min_confidence:
            return False, f"Confidence {signal.confidence:.0%} below minimum {self.min_confidence:.0%}"

        if self.allowed_symbols and signal.symbol.upper() not in self.allowed_symbols:
            return False, f"Symbol {signal.symbol} not in allowed watchlist"

        if current_price and signal.quantity > 0:
            trade_value = signal.quantity * current_price
            if trade_value > self.max_single_trade_usd:
                return False, (
                    f"Trade value ${trade_value:.2f} exceeds max ${self.max_single_trade_usd:.2f}"
                )

        return True, "Approved"

    def should_execute(self, signal: TradeSignal, force: bool = False) -> bool:
        if signal.action == TradeAction.HOLD:
            return False
        if self.dry_run and not force:
            return False
        if self.require_confirmation and not force:
            return False
        return True

    def cap_quantity(self, quantity: int, price: float) -> int:
        if price <= 0:
            return quantity
        max_shares = int(self.max_single_trade_usd / price)
        return min(quantity, max(1, max_shares))
