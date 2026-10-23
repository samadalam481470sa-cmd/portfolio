"""Settings.

Defaults live here. To change any of them, create a file named config.json in the
project folder and list only the values you want to change. Example:

    {"port": 9000, "providers": {"demo": {"product_count": 500}}}
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8800,
    # How often the engine polls providers that run live (seconds).
    "tick_seconds": 1.0,
    # How often trend and popularity scores are recalculated (seconds).
    "scores_seconds": 10,
    # Local hour (0-23) when the daily refresh and cleanup runs.
    "daily_refresh_hour": 3,
    # Price ticks older than this many days are rolled into daily summaries.
    "keep_tick_days": 3,
    "keep_search_days": 8,
    # A deal at or above both numbers raises a live alert.
    "alert_min_profit": 2.0,
    "alert_min_margin_pct": 15.0,
    "data_dir": "data",
    "import_dir": "imports",
    "providers": {
        # Demo data is simulated. It is always labeled SAMPLE in the dashboard.
        "demo": {
            "enabled": True,
            "product_count": 120,
            "updates_per_tick": 25,
            "searches_per_tick": 40,
        },
        # Watches the imports folder for CSV files with real prices.
        "csv_import": {"enabled": True, "scan_seconds": 10},
        # Optional eBay Browse API connector. Needs your own developer keys.
        "ebay": {
            "enabled": False,
            "client_id": "",
            "client_secret": "",
            "poll_seconds": 20,
            "products_per_poll": 3,
        },
    },
}


def _merge(base, extra):
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    path = ROOT / "config.json"
    if path.exists():
        _merge(cfg, json.loads(path.read_text()))
    if os.environ.get("HUB_PORT"):
        cfg["port"] = int(os.environ["HUB_PORT"])
    if os.environ.get("HUB_DATA_DIR"):
        cfg["data_dir"] = os.environ["HUB_DATA_DIR"]
    if os.environ.get("HUB_IMPORT_DIR"):
        cfg["import_dir"] = os.environ["HUB_IMPORT_DIR"]
    if os.environ.get("HUB_PRODUCTS"):
        cfg["providers"]["demo"]["product_count"] = int(os.environ["HUB_PRODUCTS"])
    return cfg


def _path(value):
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


CONFIG = load()
DATA_DIR = _path(CONFIG["data_dir"])
IMPORT_DIR = _path(CONFIG["import_dir"])
STATIC_DIR = ROOT / "static"
