"""Data source adapters for listings, markets, and public contacts."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Protocol

from estateiq.models import Contact, ListingStatus, MarketSnapshot, Property
from estateiq.repository import SQLiteRepository
from estateiq.serialization import parse_date


class DataSource(Protocol):
    """Common contract for pull-based source adapters."""

    name: str

    def collect(self) -> int:
        """Collect source records and return the number stored."""


class JsonListingSource:
    """Load listing-like records from a JSON array."""

    name = "json_listings"

    def __init__(self, path: str | Path, repository: SQLiteRepository) -> None:
        self.path = Path(path)
        self.repository = repository

    def collect(self) -> int:
        properties = [property_from_dict(record) for record in _load_array(self.path)]
        self.repository.upsert_properties(properties)
        return len(properties)


class JsonMarketSource:
    """Load ZIP/city market indicator snapshots from a JSON array."""

    name = "json_market_snapshots"

    def __init__(self, path: str | Path, repository: SQLiteRepository) -> None:
        self.path = Path(path)
        self.repository = repository

    def collect(self) -> int:
        snapshots = [MarketSnapshot(**record) for record in _load_array(self.path)]
        self.repository.upsert_market_snapshots(snapshots)
        return len(snapshots)


class JsonContactSource:
    """Load public business contact records from a JSON array."""

    name = "json_public_contacts"

    def __init__(self, path: str | Path, repository: SQLiteRepository) -> None:
        self.path = Path(path)
        self.repository = repository

    def collect(self) -> int:
        contacts = [Contact(**record) for record in _load_array(self.path)]
        self.repository.upsert_contacts(contacts)
        return len(contacts)


class DataCollectionOrchestrator:
    """Run multiple source adapters as one collection cycle."""

    def __init__(self, sources: list[DataSource]) -> None:
        self.sources = sources

    def collect_all(self) -> dict[str, int]:
        return {source.name: source.collect() for source in self.sources}


def property_from_dict(record: dict[str, object]) -> Property:
    """Create a Property while keeping unknown feed fields in metadata."""

    property_fields = {field.name for field in fields(Property)}
    known = {key: value for key, value in record.items() if key in property_fields}
    metadata = dict(known.get("metadata") or {})
    metadata.update({key: value for key, value in record.items() if key not in property_fields})
    known["metadata"] = metadata
    known["listing_status"] = ListingStatus(str(known.get("listing_status", ListingStatus.ACTIVE.value)))
    known["date_listed"] = parse_date(known.get("date_listed"))  # type: ignore[arg-type]
    return Property(**known)  # type: ignore[arg-type]


def _load_array(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list):
        raise ValueError(f"{path} must contain a JSON array")
    return records
