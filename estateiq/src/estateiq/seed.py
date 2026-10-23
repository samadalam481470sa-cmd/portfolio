"""Seed and refresh the local intelligence database."""

from __future__ import annotations

import argparse
from pathlib import Path

from estateiq.data_sources import (
    DataCollectionOrchestrator,
    JsonContactSource,
    JsonListingSource,
    JsonMarketSource,
)
from estateiq.repository import SQLiteRepository
from estateiq.scoring import InvestmentScoringEngine


DEFAULT_DATABASE_PATH = Path("estateiq.db")
DEFAULT_DATA_DIR = Path("data")


def seed_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict[str, int]:
    """Initialize schema, collect seed feeds, and score all opportunities."""

    repository = SQLiteRepository(database_path)
    try:
        repository.initialize_schema()
        data_path = Path(data_dir)
        orchestrator = DataCollectionOrchestrator(
            [
                JsonListingSource(data_path / "properties.json", repository),
                JsonMarketSource(data_path / "markets.json", repository),
                JsonContactSource(data_path / "contacts.json", repository),
            ]
        )
        counts = orchestrator.collect_all()
        scores = InvestmentScoringEngine().score_repository(repository)
        counts["investment_scores"] = len(scores)
        return counts
    finally:
        repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the EstateIQ local database.")
    parser.add_argument("--database", default=str(DEFAULT_DATABASE_PATH), help="SQLite database path")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory containing JSON feeds")
    args = parser.parse_args()
    counts = seed_database(args.database, args.data_dir)
    for source, count in counts.items():
        print(f"{source}: {count}")


if __name__ == "__main__":
    main()
