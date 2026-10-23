"""Dynamic position sizing based on capital, confidence, and growth phase."""

from __future__ import annotations


class PositionSizer:
    """Sizes trades to grow capital while limiting risk per trade."""

    def __init__(
        self,
        risk_per_trade_pct: float = 0.03,
        max_position_pct: float = 0.15,
        min_trade_usd: float = 10.0,
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_position_pct = max_position_pct
        self.min_trade_usd = min_trade_usd

    def size_stock_order(
        self,
        available_capital: float,
        price: float,
        confidence: float,
        multiplier: float = 1.0,
    ) -> int:
        """Return number of shares to buy based on capital and confidence."""
        if price <= 0 or available_capital <= 0:
            return 0

        # Scale aggression slightly as we grow (but cap it)
        growth_boost = min(multiplier, 2.0)
        risk_budget = available_capital * self.risk_per_trade_pct * confidence * growth_boost
        max_position = available_capital * self.max_position_pct
        trade_usd = min(risk_budget, max_position)
        trade_usd = max(trade_usd, self.min_trade_usd) if trade_usd >= self.min_trade_usd else 0

        if trade_usd <= 0:
            return 0
        return max(1, int(trade_usd / price))

    def size_contract_order(
        self,
        available_capital: float,
        contract_price: float,
        confidence: float,
        multiplier: float = 1.0,
    ) -> int:
        """Size prediction market contracts (price 0.01-0.99 or cents)."""
        if contract_price <= 0:
            return 0
        # Normalize if price is in cents (1-99)
        price = contract_price / 100 if contract_price > 1 else contract_price
        cost_per_contract = price
        growth_boost = min(multiplier, 2.0)
        risk_budget = available_capital * self.risk_per_trade_pct * confidence * growth_boost
        max_position = available_capital * self.max_position_pct
        trade_usd = min(risk_budget, max_position)
        if trade_usd < self.min_trade_usd:
            return 0
        return max(1, int(trade_usd / cost_per_contract))

    def platform_budget(self, total_capital: float, allocation_pct: float) -> float:
        return total_capital * allocation_pct
