"""Replit-friendly launcher for the EstateIQ website.

Run this file with Python. Do not paste shell commands into it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from estateiq.api import run_server  # noqa: E402


def main() -> None:
    """Start the EstateIQ website with seeded demo data."""

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    database_path = os.environ.get("ESTATEIQ_DATABASE", "estateiq.db")
    run_server(host=host, port=port, database_path=database_path, seed=True)


if __name__ == "__main__":
    main()
