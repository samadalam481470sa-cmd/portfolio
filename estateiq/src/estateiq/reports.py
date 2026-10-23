"""AI-style investment report generation from structured opportunity data."""

from __future__ import annotations

from estateiq.models import Contact, InvestmentReport, InvestmentScore, MarketSnapshot, Property


class InvestmentReportGenerator:
    """Create concise narrative reports without requiring an external LLM."""

    def generate(
        self,
        property_: Property,
        score: InvestmentScore,
        market: MarketSnapshot,
        contacts: list[Contact],
    ) -> InvestmentReport:
        title = f"{property_.address}, {property_.city}, {property_.state} - {score.recommendation}"
        summary = (
            f"This {property_.property_type} opportunity scores {score.score:.1f}/100. "
            f"The model estimates a {score.cap_rate_pct:.1f}% cap rate and "
            f"${score.annual_cash_flow:,.0f} in annual cash flow, supported by "
            f"{market.rent_growth_pct:.1f}% rent growth and {market.job_growth_pct:.1f}% job growth."
        )
        positives = tuple(score.reasons)
        risks = tuple(self._risks(property_, score, market, contacts))
        next_steps = tuple(self._next_steps(property_, contacts))
        return InvestmentReport(
            property_source_id=property_.source_id,
            title=title,
            executive_summary=summary,
            positives=positives,
            risks=risks,
            next_steps=next_steps,
        )

    @staticmethod
    def _risks(
        property_: Property,
        score: InvestmentScore,
        market: MarketSnapshot,
        contacts: list[Contact],
    ) -> list[str]:
        risks: list[str] = []
        if score.annual_cash_flow < 0:
            risks.append("Modeled cash flow is negative before investor-specific financing assumptions.")
        if score.cap_rate_pct < 5.5:
            risks.append("Cap rate is below the preferred threshold for income-focused acquisitions.")
        if market.inventory_level > 800:
            risks.append("Inventory is elevated, which can weaken pricing power.")
        if market.days_on_market > 70:
            risks.append("Days on market are high relative to fast-moving expansion markets.")
        if property_.price_per_square_foot and property_.price_per_square_foot > market.median_price_per_sqft:
            risks.append("Listing price is above the local median price per square foot.")
        if not contacts:
            risks.append("No public contact record is currently linked to this opportunity.")
        return risks or ["No major model-level risks detected; verify condition, rents, and title history."]

    @staticmethod
    def _next_steps(property_: Property, contacts: list[Contact]) -> list[str]:
        steps = [
            "Validate rent estimate against active comparable leases.",
            "Review public records for liens, permits, assessed value, and ownership history.",
            "Underwrite financing terms, taxes, insurance, repairs, and vacancy assumptions.",
        ]
        if contacts:
            primary_contact = contacts[0]
            contact_hint = primary_contact.email or primary_contact.phone or primary_contact.website
            if contact_hint:
                steps.append(f"Contact {primary_contact.name} ({primary_contact.role}) via {contact_hint}.")
        else:
            steps.append("Search county records and broker directories for a verified public contact.")
        return steps
