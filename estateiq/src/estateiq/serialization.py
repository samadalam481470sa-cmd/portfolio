"""Serialization helpers for model construction and API responses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


def parse_date(value: str | date | None) -> date | None:
    """Parse ISO date values while allowing already parsed dates."""

    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def json_ready(value: Any) -> Any:
    """Convert dataclasses, dates, enums, and tuples into JSON-safe values."""

    if is_dataclass(value):
        return {key: json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
