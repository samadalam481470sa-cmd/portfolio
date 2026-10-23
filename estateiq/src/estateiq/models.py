"""Core data models for properties, market signals, contacts, and scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any


class ListingStatus(str, Enum):
    """Supported lifecycle states for a property opportunity."""

    ACTIVE = "active"
    PENDING = "pending"
    SOLD = "sold"
    OFF_MARKET = "off_market"
    FORECLOSURE = "foreclosure"
    AUCTION = "auction"


@dataclass(frozen=True)
class Property:
    """A normalized investment property listing from any supported source."""

    source_id: str
    address: str
    city: str
    county: str
    state: str
    zip_code: str
    latitude: float
    longitude: float
    price: float
    bedrooms: int | None = None
    bathrooms: float | None = None
    square_footage: int | None = None
    lot_size_sqft: int | None = None
    listing_status: ListingStatus = ListingStatus.ACTIVE
    listing_source: str = "unknown"
    date_listed: date | None = None
    property_type: str = "residential"
    estimated_monthly_rent: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def price_per_square_foot(self) -> float | None:
        """Return the asking price per interior square foot when available."""

        if not self.square_footage:
            return None
        return self.price / self.square_footage


@dataclass(frozen=True)
class MarketSnapshot:
    """Market indicators for a ZIP code or city over a given period."""

    market_id: str
    city: str
    county: str
    state: str
    zip_code: str
    period: str
    median_price: float
    median_price_per_sqft: float
    average_rent: float
    rent_growth_pct: float
    inventory_level: int
    days_on_market: float
    sales_volume: int
    appreciation_pct: float
    population_growth_pct: float
    job_growth_pct: float
    building_permit_growth_pct: float
    new_business_growth_pct: float
    housing_demand_index: float


@dataclass(frozen=True)
class Contact:
    """A publicly available business contact related to a property or market."""

    contact_id: str
    name: str
    role: str
    brokerage: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    business_address: str | None = None
    city: str | None = None
    state: str | None = None
    source: str = "public_record"
    property_source_id: str | None = None

    @property
    def completeness_score(self) -> float:
        """Score how contactable this record is from 0.0 to 1.0."""

        fields = [self.phone, self.email, self.website, self.business_address]
        return sum(1 for value in fields if value) / len(fields)


@dataclass(frozen=True)
class InvestmentScore:
    """A scored property opportunity with component explanations."""

    property_source_id: str
    score: float
    cap_rate_pct: float
    annual_cash_flow: float
    market_strength: float
    value_score: float
    demand_score: float
    recommendation: str
    reasons: tuple[str, ...]
    calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class InvestmentReport:
    """A concise investment thesis for a property opportunity."""

    property_source_id: str
    title: str
    executive_summary: str
    positives: tuple[str, ...]
    risks: tuple[str, ...]
    next_steps: tuple[str, ...]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
