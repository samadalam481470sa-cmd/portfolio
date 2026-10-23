"""Investment scoring and ranking logic."""

from __future__ import annotations

from estateiq.models import InvestmentScore, MarketSnapshot, Property
from estateiq.repository import SQLiteRepository


class InvestmentScoringEngine:
    """Calculate normalized opportunity scores from property and market data."""

    def __init__(self, expense_ratio: float = 0.38) -> None:
        self.expense_ratio = expense_ratio

    def score_property(self, property_: Property, market: MarketSnapshot) -> InvestmentScore:
        estimated_rent = property_.estimated_monthly_rent or market.average_rent
        annual_noi = estimated_rent * 12 * (1 - self.expense_ratio)
        cap_rate_pct = (annual_noi / property_.price) * 100 if property_.price else 0
        annual_cash_flow = annual_noi - (property_.price * 0.065)
        value_score = self._value_score(property_, market)
        market_strength = self._market_strength(market)
        demand_score = self._demand_score(market)
        cash_flow_score = _scale(cap_rate_pct, low=3.0, high=10.0)
        composite = (
            cash_flow_score * 0.28
            + _scale(annual_cash_flow, low=-12000, high=18000) * 0.22
            + market_strength * 0.24
            + value_score * 0.16
            + demand_score * 0.10
        )
        reasons = self._reasons(
            cap_rate_pct=cap_rate_pct,
            annual_cash_flow=annual_cash_flow,
            market_strength=market_strength,
            value_score=value_score,
            demand_score=demand_score,
            market=market,
        )
        return InvestmentScore(
            property_source_id=property_.source_id,
            score=round(composite, 2),
            cap_rate_pct=round(cap_rate_pct, 2),
            annual_cash_flow=round(annual_cash_flow, 2),
            market_strength=round(market_strength, 2),
            value_score=round(value_score, 2),
            demand_score=round(demand_score, 2),
            recommendation=self._recommendation(composite),
            reasons=tuple(reasons),
        )

    def score_repository(self, repository: SQLiteRepository) -> list[InvestmentScore]:
        """Score every property with a matching latest market snapshot."""

        scores: list[InvestmentScore] = []
        for property_ in repository.list_properties():
            market = repository.latest_market_for_zip(property_.zip_code)
            if market is None:
                continue
            scores.append(self.score_property(property_, market))
        repository.upsert_scores(scores)
        return sorted(scores, key=lambda score: score.score, reverse=True)

    @staticmethod
    def _value_score(property_: Property, market: MarketSnapshot) -> float:
        price_per_square_foot = property_.price_per_square_foot
        if price_per_square_foot is None:
            return 50.0
        discount_pct = ((market.median_price_per_sqft - price_per_square_foot) / market.median_price_per_sqft) * 100
        return _scale(discount_pct, low=-15, high=25)

    @staticmethod
    def _market_strength(market: MarketSnapshot) -> float:
        return round(
            _scale(market.population_growth_pct, low=-1, high=5) * 0.20
            + _scale(market.job_growth_pct, low=-1, high=6) * 0.20
            + _scale(market.rent_growth_pct, low=0, high=10) * 0.18
            + _scale(market.appreciation_pct, low=-2, high=12) * 0.18
            + _scale(market.building_permit_growth_pct, low=-5, high=20) * 0.12
            + _scale(market.new_business_growth_pct, low=-2, high=15) * 0.12,
            2,
        )

    @staticmethod
    def _demand_score(market: MarketSnapshot) -> float:
        inventory_pressure = 100 - _scale(market.inventory_level, low=150, high=1200)
        speed = 100 - _scale(market.days_on_market, low=20, high=95)
        demand = _clamp(market.housing_demand_index)
        return round(inventory_pressure * 0.35 + speed * 0.30 + demand * 0.35, 2)

    @staticmethod
    def _recommendation(score: float) -> str:
        if score >= 80:
            return "Priority target"
        if score >= 65:
            return "Strong watchlist"
        if score >= 50:
            return "Needs underwriting"
        return "Monitor only"

    @staticmethod
    def _reasons(
        *,
        cap_rate_pct: float,
        annual_cash_flow: float,
        market_strength: float,
        value_score: float,
        demand_score: float,
        market: MarketSnapshot,
    ) -> list[str]:
        reasons: list[str] = []
        if cap_rate_pct >= 7:
            reasons.append(f"Estimated cap rate is attractive at {cap_rate_pct:.1f}%.")
        if annual_cash_flow > 0:
            reasons.append(f"Projected annual cash flow is positive at ${annual_cash_flow:,.0f}.")
        if market_strength >= 70:
            reasons.append(
                f"{market.city} shows strong growth signals across jobs, population, rents, and permits."
            )
        if value_score >= 65:
            reasons.append("Asking price is meaningfully below the local median price per square foot.")
        if demand_score >= 70:
            reasons.append("Low inventory and fast days-on-market suggest strong housing demand.")
        if not reasons:
            reasons.append("Opportunity requires deeper underwriting before prioritization.")
        return reasons


def _scale(value: float, *, low: float, high: float) -> float:
    if high == low:
        return 0.0
    return _clamp(((value - low) / (high - low)) * 100)


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))
