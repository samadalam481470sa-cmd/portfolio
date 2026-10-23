"""SQLite repository for the real estate intelligence data stores."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from estateiq.models import Contact, InvestmentScore, ListingStatus, MarketSnapshot, Property
from estateiq.serialization import parse_date


class SQLiteRepository:
    """Persistence boundary for property, market, contact, and score data."""

    def __init__(self, database_path: str | Path = "estateiq.db") -> None:
        self.database_path = Path(database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def initialize_schema(self) -> None:
        """Create the three core databases plus a derived score table."""

        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS properties (
                source_id TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                county TEXT NOT NULL,
                state TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                price REAL NOT NULL,
                bedrooms INTEGER,
                bathrooms REAL,
                square_footage INTEGER,
                lot_size_sqft INTEGER,
                listing_status TEXT NOT NULL,
                listing_source TEXT NOT NULL,
                date_listed TEXT,
                property_type TEXT NOT NULL,
                estimated_monthly_rent REAL,
                metadata TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS market_snapshots (
                market_id TEXT PRIMARY KEY,
                city TEXT NOT NULL,
                county TEXT NOT NULL,
                state TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                period TEXT NOT NULL,
                median_price REAL NOT NULL,
                median_price_per_sqft REAL NOT NULL,
                average_rent REAL NOT NULL,
                rent_growth_pct REAL NOT NULL,
                inventory_level INTEGER NOT NULL,
                days_on_market REAL NOT NULL,
                sales_volume INTEGER NOT NULL,
                appreciation_pct REAL NOT NULL,
                population_growth_pct REAL NOT NULL,
                job_growth_pct REAL NOT NULL,
                building_permit_growth_pct REAL NOT NULL,
                new_business_growth_pct REAL NOT NULL,
                housing_demand_index REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contacts (
                contact_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                brokerage TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                business_address TEXT,
                city TEXT,
                state TEXT,
                source TEXT NOT NULL,
                property_source_id TEXT
            );

            CREATE TABLE IF NOT EXISTS investment_scores (
                property_source_id TEXT PRIMARY KEY,
                score REAL NOT NULL,
                cap_rate_pct REAL NOT NULL,
                annual_cash_flow REAL NOT NULL,
                market_strength REAL NOT NULL,
                value_score REAL NOT NULL,
                demand_score REAL NOT NULL,
                recommendation TEXT NOT NULL,
                reasons TEXT NOT NULL,
                calculated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_properties_market
                ON properties (state, city, zip_code);
            CREATE INDEX IF NOT EXISTS idx_market_zip_period
                ON market_snapshots (zip_code, period);
            CREATE INDEX IF NOT EXISTS idx_contacts_property
                ON contacts (property_source_id);
            """
        )
        self.connection.commit()

    def upsert_properties(self, properties: Iterable[Property]) -> None:
        rows = [
            (
                property_.source_id,
                property_.address,
                property_.city,
                property_.county,
                property_.state,
                property_.zip_code,
                property_.latitude,
                property_.longitude,
                property_.price,
                property_.bedrooms,
                property_.bathrooms,
                property_.square_footage,
                property_.lot_size_sqft,
                property_.listing_status.value,
                property_.listing_source,
                property_.date_listed.isoformat() if property_.date_listed else None,
                property_.property_type,
                property_.estimated_monthly_rent,
                json.dumps(property_.metadata, sort_keys=True),
            )
            for property_ in properties
        ]
        self.connection.executemany(
            """
            INSERT INTO properties VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                address=excluded.address,
                city=excluded.city,
                county=excluded.county,
                state=excluded.state,
                zip_code=excluded.zip_code,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                price=excluded.price,
                bedrooms=excluded.bedrooms,
                bathrooms=excluded.bathrooms,
                square_footage=excluded.square_footage,
                lot_size_sqft=excluded.lot_size_sqft,
                listing_status=excluded.listing_status,
                listing_source=excluded.listing_source,
                date_listed=excluded.date_listed,
                property_type=excluded.property_type,
                estimated_monthly_rent=excluded.estimated_monthly_rent,
                metadata=excluded.metadata
            """,
            rows,
        )
        self.connection.commit()

    def upsert_market_snapshots(self, snapshots: Iterable[MarketSnapshot]) -> None:
        rows = [tuple(snapshot.__dict__.values()) for snapshot in snapshots]
        self.connection.executemany(
            """
            INSERT INTO market_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
                city=excluded.city,
                county=excluded.county,
                state=excluded.state,
                zip_code=excluded.zip_code,
                period=excluded.period,
                median_price=excluded.median_price,
                median_price_per_sqft=excluded.median_price_per_sqft,
                average_rent=excluded.average_rent,
                rent_growth_pct=excluded.rent_growth_pct,
                inventory_level=excluded.inventory_level,
                days_on_market=excluded.days_on_market,
                sales_volume=excluded.sales_volume,
                appreciation_pct=excluded.appreciation_pct,
                population_growth_pct=excluded.population_growth_pct,
                job_growth_pct=excluded.job_growth_pct,
                building_permit_growth_pct=excluded.building_permit_growth_pct,
                new_business_growth_pct=excluded.new_business_growth_pct,
                housing_demand_index=excluded.housing_demand_index
            """,
            rows,
        )
        self.connection.commit()

    def upsert_contacts(self, contacts: Iterable[Contact]) -> None:
        rows = [tuple(contact.__dict__.values()) for contact in contacts]
        self.connection.executemany(
            """
            INSERT INTO contacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact_id) DO UPDATE SET
                name=excluded.name,
                role=excluded.role,
                brokerage=excluded.brokerage,
                phone=excluded.phone,
                email=excluded.email,
                website=excluded.website,
                business_address=excluded.business_address,
                city=excluded.city,
                state=excluded.state,
                source=excluded.source,
                property_source_id=excluded.property_source_id
            """,
            rows,
        )
        self.connection.commit()

    def upsert_scores(self, scores: Iterable[InvestmentScore]) -> None:
        rows = [
            (
                score.property_source_id,
                score.score,
                score.cap_rate_pct,
                score.annual_cash_flow,
                score.market_strength,
                score.value_score,
                score.demand_score,
                score.recommendation,
                json.dumps(list(score.reasons)),
                score.calculated_at.isoformat(),
            )
            for score in scores
        ]
        self.connection.executemany(
            """
            INSERT INTO investment_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(property_source_id) DO UPDATE SET
                score=excluded.score,
                cap_rate_pct=excluded.cap_rate_pct,
                annual_cash_flow=excluded.annual_cash_flow,
                market_strength=excluded.market_strength,
                value_score=excluded.value_score,
                demand_score=excluded.demand_score,
                recommendation=excluded.recommendation,
                reasons=excluded.reasons,
                calculated_at=excluded.calculated_at
            """,
            rows,
        )
        self.connection.commit()

    def list_properties(
        self,
        *,
        state: str | None = None,
        city: str | None = None,
        status: ListingStatus | None = None,
    ) -> list[Property]:
        query = "SELECT * FROM properties WHERE 1 = 1"
        params: list[str] = []
        if state:
            query += " AND state = ?"
            params.append(state)
        if city:
            query += " AND city = ?"
            params.append(city)
        if status:
            query += " AND listing_status = ?"
            params.append(status.value)
        rows = self.connection.execute(query + " ORDER BY date_listed DESC", params).fetchall()
        return [self._property_from_row(row) for row in rows]

    def get_property(self, source_id: str) -> Property | None:
        row = self.connection.execute(
            "SELECT * FROM properties WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        return self._property_from_row(row) if row else None

    def latest_market_for_zip(self, zip_code: str) -> MarketSnapshot | None:
        row = self.connection.execute(
            """
            SELECT * FROM market_snapshots
            WHERE zip_code = ?
            ORDER BY period DESC
            LIMIT 1
            """,
            (zip_code,),
        ).fetchone()
        return self._market_from_row(row) if row else None

    def contacts_for_property(self, property_: Property) -> list[Contact]:
        rows = self.connection.execute(
            """
            SELECT * FROM contacts
            WHERE property_source_id = ?
               OR (property_source_id IS NULL AND city = ? AND state = ?)
            ORDER BY property_source_id DESC, name
            """,
            (property_.source_id, property_.city, property_.state),
        ).fetchall()
        return [self._contact_from_row(row) for row in rows]

    def list_scores(self) -> list[InvestmentScore]:
        rows = self.connection.execute(
            "SELECT * FROM investment_scores ORDER BY score DESC"
        ).fetchall()
        return [self._score_from_row(row) for row in rows]

    def get_score(self, property_source_id: str) -> InvestmentScore | None:
        row = self.connection.execute(
            "SELECT * FROM investment_scores WHERE property_source_id = ?",
            (property_source_id,),
        ).fetchone()
        return self._score_from_row(row) if row else None

    def ranked_opportunities(self, limit: int = 25) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT p.*, s.score, s.cap_rate_pct, s.annual_cash_flow, s.market_strength,
                   s.property_source_id, s.value_score, s.demand_score, s.recommendation,
                   s.reasons, s.calculated_at
            FROM properties p
            JOIN investment_scores s ON p.source_id = s.property_source_id
            ORDER BY s.score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        opportunities: list[dict[str, object]] = []
        for row in rows:
            property_ = self._property_from_row(row)
            opportunities.append(
                {
                    "property": property_,
                    "score": self._score_from_row(row),
                    "market": self.latest_market_for_zip(property_.zip_code),
                    "contacts": self.contacts_for_property(property_),
                }
            )
        return opportunities

    @staticmethod
    def _property_from_row(row: sqlite3.Row) -> Property:
        return Property(
            source_id=row["source_id"],
            address=row["address"],
            city=row["city"],
            county=row["county"],
            state=row["state"],
            zip_code=row["zip_code"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            price=row["price"],
            bedrooms=row["bedrooms"],
            bathrooms=row["bathrooms"],
            square_footage=row["square_footage"],
            lot_size_sqft=row["lot_size_sqft"],
            listing_status=ListingStatus(row["listing_status"]),
            listing_source=row["listing_source"],
            date_listed=parse_date(row["date_listed"]),
            property_type=row["property_type"],
            estimated_monthly_rent=row["estimated_monthly_rent"],
            metadata=json.loads(row["metadata"]),
        )

    @staticmethod
    def _market_from_row(row: sqlite3.Row) -> MarketSnapshot:
        return MarketSnapshot(**{field: row[field] for field in MarketSnapshot.__dataclass_fields__})

    @staticmethod
    def _contact_from_row(row: sqlite3.Row) -> Contact:
        return Contact(**{field: row[field] for field in Contact.__dataclass_fields__})

    @staticmethod
    def _score_from_row(row: sqlite3.Row) -> InvestmentScore:
        return InvestmentScore(
            property_source_id=row["property_source_id"],
            score=row["score"],
            cap_rate_pct=row["cap_rate_pct"],
            annual_cash_flow=row["annual_cash_flow"],
            market_strength=row["market_strength"],
            value_score=row["value_score"],
            demand_score=row["demand_score"],
            recommendation=row["recommendation"],
            reasons=tuple(json.loads(row["reasons"])),
            calculated_at=datetime.fromisoformat(row["calculated_at"]),
        )
