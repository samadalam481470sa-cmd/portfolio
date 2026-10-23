"""The five databases.

Each database is its own SQLite file in the data folder:

  catalog.db  - products: what exists
  prices.db   - offers: who sells it and for how much, plus price history
  trends.db   - searches, sales ranks, and the trend and popularity scores
  opps.db     - profitable buy-here, sell-there pairs, plus alerts
  sources.db  - stores, fees, how-to-buy steps, provider health, import log

Every connection attaches all five, so a query can join across them with names
like prices.offers or catalog.products. Reads never block writes (WAL mode).
Writes go through write(), which allows one writer at a time.
"""
import sqlite3
import threading
from contextlib import contextmanager

from .config import DATA_DIR

NAMES = ["catalog", "prices", "trends", "opps", "sources"]

SCHEMAS = {
    "catalog": """
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY,
            pkey TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            brand TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'General',
            upc TEXT NOT NULL DEFAULT '',
            is_sample INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
        CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
    """,
    "prices": """
        CREATE TABLE IF NOT EXISTS offers(
            product_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            price REAL NOT NULL,
            pack_qty INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL,
            in_stock INTEGER NOT NULL DEFAULT 1,
            url TEXT NOT NULL DEFAULT '',
            url_kind TEXT NOT NULL DEFAULT 'search',
            seller TEXT NOT NULL DEFAULT '',
            is_sample INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(product_id, source)
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS idx_offers_source ON offers(source);
        CREATE TABLE IF NOT EXISTS ticks(
            product_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            ts INTEGER NOT NULL,
            unit_price REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ticks_key ON ticks(product_id, source, ts);
        CREATE INDEX IF NOT EXISTS idx_ticks_ts ON ticks(ts);
        CREATE TABLE IF NOT EXISTS daily(
            product_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            day TEXT NOT NULL,
            lo REAL, hi REAL, avg REAL, close REAL,
            PRIMARY KEY(product_id, source, day)
        ) WITHOUT ROWID;
    """,
    "trends": """
        CREATE TABLE IF NOT EXISTS search_buckets(
            product_id INTEGER NOT NULL,
            minute INTEGER NOT NULL,
            searches INTEGER NOT NULL,
            PRIMARY KEY(product_id, minute)
        ) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS sales_signals(
            product_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            sales_rank INTEGER,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(product_id, source)
        ) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS scores(
            product_id INTEGER PRIMARY KEY,
            searches_15m INTEGER NOT NULL DEFAULT 0,
            searches_prev_45m INTEGER NOT NULL DEFAULT 0,
            searches_24h INTEGER NOT NULL DEFAULT 0,
            trend_score REAL NOT NULL DEFAULT 0,
            popularity_score REAL NOT NULL DEFAULT 0,
            best_rank INTEGER,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scores_trend ON scores(trend_score DESC);
        CREATE INDEX IF NOT EXISTS idx_scores_pop ON scores(popularity_score DESC);
        CREATE INDEX IF NOT EXISTS idx_scores_24h ON scores(searches_24h DESC);
    """,
    "opps": """
        CREATE TABLE IF NOT EXISTS opportunities(
            product_id INTEGER NOT NULL,
            buy_source TEXT NOT NULL,
            sell_source TEXT NOT NULL,
            buy_unit REAL NOT NULL,
            buy_pack_qty INTEGER NOT NULL,
            sell_price REAL NOT NULL,
            sell_pack_qty INTEGER NOT NULL,
            cost REAL NOT NULL,
            fees REAL NOT NULL,
            ship REAL NOT NULL,
            profit REAL NOT NULL,
            margin_pct REAL NOT NULL,
            roi_pct REAL NOT NULL,
            sales_per_pack REAL NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(product_id, buy_source, sell_source)
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS idx_opps_profit ON opportunities(profit DESC);
        CREATE INDEX IF NOT EXISTS idx_opps_margin ON opportunities(margin_pct DESC);
        CREATE INDEX IF NOT EXISTS idx_opps_roi ON opportunities(roi_pct DESC);
        CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            buy_source TEXT NOT NULL,
            sell_source TEXT NOT NULL,
            profit REAL NOT NULL,
            margin_pct REAL NOT NULL
        );
    """,
    "sources": """
        CREATE TABLE IF NOT EXISTS sources(
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            fee_pct REAL NOT NULL DEFAULT 0,
            ship_per_sale REAL NOT NULL DEFAULT 0,
            search_url TEXT NOT NULL DEFAULT '',
            membership TEXT NOT NULL DEFAULT '',
            how_to_buy TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS provider_status(
            provider TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run INTEGER,
            last_ok INTEGER,
            last_error TEXT NOT NULL DEFAULT '',
            rows_total INTEGER NOT NULL DEFAULT 0,
            note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS import_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            filename TEXT NOT NULL,
            rows_ok INTEGER NOT NULL,
            rows_bad INTEGER NOT NULL,
            message TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """,
}

WRITE_LOCK = threading.RLock()
_local = threading.local()


def path(name):
    return DATA_DIR / f"{name}.db"


def init_all():
    """Create the data folder and all five database files."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        con = sqlite3.connect(str(path(name)))
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMAS[name])
        con.commit()
        con.close()


def db():
    """Return this thread's connection, with all five databases attached."""
    con = getattr(_local, "con", None)
    if con is None:
        con = sqlite3.connect(
            ":memory:", isolation_level=None, check_same_thread=False, timeout=30
        )
        con.row_factory = sqlite3.Row
        for name in NAMES:
            con.execute(f"ATTACH DATABASE ? AS {name}", (str(path(name)),))
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")
        _local.con = con
    return con


@contextmanager
def write():
    """One writer at a time. Commits on success, rolls back on error."""
    con = db()
    with WRITE_LOCK:
        con.execute("BEGIN IMMEDIATE")
        try:
            yield con
        except BaseException:
            con.execute("ROLLBACK")
            raise
        else:
            con.execute("COMMIT")


def rows(sql, params=()):
    return [dict(r) for r in db().execute(sql, params).fetchall()]


def one(sql, params=()):
    r = db().execute(sql, params).fetchone()
    return None if r is None else r[0]
