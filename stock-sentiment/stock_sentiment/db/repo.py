"""SQLite storage. Plain sqlite3 keeps the dependency surface small; swap for Postgres later if needed."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

from ..models import Article, Mention, SentimentScore

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    summary TEXT,
    body TEXT,
    publisher TEXT,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    title_hash TEXT NOT NULL,
    ticker_hints TEXT,
    linked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_articles_title_hash ON articles(title_hash);
CREATE INDEX IF NOT EXISTS ix_articles_published ON articles(published_at);

CREATE TABLE IF NOT EXISTS mentions (
    article_id TEXT NOT NULL REFERENCES articles(id),
    ticker TEXT NOT NULL,
    relevance REAL NOT NULL,
    location TEXT NOT NULL,
    novelty REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (article_id, ticker)
);
CREATE INDEX IF NOT EXISTS ix_mentions_ticker ON mentions(ticker);

CREATE TABLE IF NOT EXISTS sentiment (
    article_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    model TEXT NOT NULL,
    pos REAL, neg REAL, neu REAL, compound REAL,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (article_id, ticker, model)
);

CREATE TABLE IF NOT EXISTS signals (
    ticker TEXT NOT NULL,
    as_of TEXT NOT NULL,
    model TEXT NOT NULL,
    score REAL, baseline REAL, delta REAL, volume_z REAL,
    confidence REAL, composite REAL, n_articles INTEGER,
    top_headlines TEXT,
    PRIMARY KEY (ticker, as_of, model)
);

CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS http_cache (
    url TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    n_items INTEGER NOT NULL,
    n_new INTEGER NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    ticker TEXT NOT NULL,
    day TEXT NOT NULL,
    direction TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (ticker, day, direction)
);
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repo:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.conn:
            yield self.conn

    # ---- articles -------------------------------------------------------
    def has_article(self, article_id: str, url: str, title_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM articles WHERE id=? OR url=? OR title_hash=? LIMIT 1",
            (article_id, url, title_hash),
        ).fetchone()
        return row is not None

    def insert_article(self, a: Article) -> bool:
        """Insert if new. Returns False when it is an exact duplicate (same URL or same normalized title)."""
        if self.has_article(a.id, a.url, a.title_hash):
            # Same story from another feed: merge the ticker hints so linking sees them.
            if a.ticker_hints:
                self._merge_hints(a)
            return False
        with self.tx() as c:
            c.execute(
                """INSERT INTO articles (id, source, url, title, summary, body, publisher, published_at,
                                         fetched_at, title_hash, ticker_hints)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (a.id, a.source, a.url, a.title, a.summary, a.body, a.publisher, _iso(a.published_at),
                 _iso(a.fetched_at), a.title_hash, json.dumps(sorted(set(a.ticker_hints)))),
            )
        return True

    def _merge_hints(self, a: Article) -> None:
        row = self.conn.execute(
            "SELECT id, ticker_hints FROM articles WHERE id=? OR url=? OR title_hash=? LIMIT 1",
            (a.id, a.url, a.title_hash),
        ).fetchone()
        hints = set(json.loads(row["ticker_hints"] or "[]"))
        merged = hints | set(a.ticker_hints)
        if merged != hints:
            with self.tx() as c:
                c.execute("UPDATE articles SET ticker_hints=?, linked=0 WHERE id=?",
                          (json.dumps(sorted(merged)), row["id"]))

    def reset_links(self) -> None:
        """Force every article to be re-linked (and re-scored) after linker rules or the universe change."""
        with self.tx() as c:
            c.execute("UPDATE articles SET linked=0")

    def unlinked_articles(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM articles WHERE linked=0 ORDER BY published_at").fetchall()

    def save_mentions(self, article_id: str, mentions: Iterable[Mention]) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM mentions WHERE article_id=?", (article_id,))
            c.execute("DELETE FROM sentiment WHERE article_id=?", (article_id,))
            c.executemany(
                "INSERT INTO mentions (article_id, ticker, relevance, location, novelty) VALUES (?,?,?,?,?)",
                [(m.article_id, m.ticker, m.relevance, m.location, m.novelty) for m in mentions],
            )
            c.execute("UPDATE articles SET linked=1 WHERE id=?", (article_id,))

    def recent_titles(self, ticker: str, before: str, hours: float) -> list[str]:
        since = _iso(datetime.fromisoformat(before) - timedelta(hours=hours))
        rows = self.conn.execute(
            """SELECT a.title FROM mentions m JOIN articles a ON a.id = m.article_id
               WHERE m.ticker=? AND a.published_at < ? AND a.published_at >= ?""",
            (ticker, before, since),
        ).fetchall()
        return [r["title"] for r in rows]

    # ---- sentiment ------------------------------------------------------
    def unscored_mentions(self, model: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT m.article_id, m.ticker, a.title, a.summary, a.body
               FROM mentions m JOIN articles a ON a.id = m.article_id
               LEFT JOIN sentiment s ON s.article_id = m.article_id AND s.ticker = m.ticker AND s.model = ?
               WHERE s.article_id IS NULL""",
            (model,),
        ).fetchall()

    def save_sentiment(self, rows: list[tuple[str, str, str, SentimentScore]]) -> None:
        now = _iso(utcnow())
        with self.tx() as c:
            c.executemany(
                """INSERT OR REPLACE INTO sentiment (article_id, ticker, model, pos, neg, neu, compound, scored_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(aid, t, model, s.pos, s.neg, s.neu, s.compound, now) for aid, t, model, s in rows],
            )

    def scored_items(self, model: str, tickers: list[str] | None = None) -> pd.DataFrame:
        """Every scored (article, ticker) pair with the fields aggregation needs."""
        q = """SELECT m.ticker, a.id AS article_id, a.title, a.url, a.source, a.publisher, a.published_at,
                      m.relevance, m.novelty, s.compound
               FROM mentions m
               JOIN articles a ON a.id = m.article_id
               JOIN sentiment s ON s.article_id = m.article_id AND s.ticker = m.ticker AND s.model = ?"""
        params: list = [model]
        if tickers:
            q += f" WHERE m.ticker IN ({','.join('?' * len(tickers))})"
            params += tickers
        df = pd.read_sql_query(q, self.conn, params=params)
        df["published_at"] = pd.to_datetime(df["published_at"], utc=True, format="ISO8601")
        return df

    # ---- signals --------------------------------------------------------
    def save_signals(self, model: str, as_of: datetime, rows: list[dict]) -> None:
        with self.tx() as c:
            c.executemany(
                """INSERT OR REPLACE INTO signals (ticker, as_of, model, score, baseline, delta, volume_z,
                                                   confidence, composite, n_articles, top_headlines)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [(r["ticker"], _iso(as_of), model, r["score"], r["baseline"], r["delta"], r["volume_z"],
                  r["confidence"], r["composite"], r["n_articles"], json.dumps(r["top_headlines"]))
                 for r in rows],
            )

    def latest_signals(self, model: str) -> pd.DataFrame:
        return pd.read_sql_query(
            """SELECT * FROM signals WHERE model=? AND as_of = (SELECT MAX(as_of) FROM signals WHERE model=?)
               ORDER BY composite DESC""",
            self.conn, params=[model, model],
        )

    def signal_history(self, ticker: str, model: str) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM signals WHERE ticker=? AND model=? ORDER BY as_of",
                               self.conn, params=[ticker, model])
        df["as_of"] = pd.to_datetime(df["as_of"], utc=True, format="ISO8601")
        return df

    # ---- prices ---------------------------------------------------------
    def save_prices(self, df: pd.DataFrame) -> None:
        with self.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO prices (ticker, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                df[["ticker", "date", "open", "high", "low", "close", "volume"]].itertuples(index=False, name=None),
            )

    def prices(self, tickers: list[str] | None = None) -> pd.DataFrame:
        q, params = "SELECT * FROM prices", []
        if tickers:
            q += f" WHERE ticker IN ({','.join('?' * len(tickers))})"
            params = tickers
        df = pd.read_sql_query(q + " ORDER BY date", self.conn, params=params)
        df["date"] = pd.to_datetime(df["date"])
        return df

    def last_price_date(self, ticker: str) -> str | None:
        row = self.conn.execute("SELECT MAX(date) AS d FROM prices WHERE ticker=?", (ticker,)).fetchone()
        return row["d"]

    # ---- http cache -----------------------------------------------------
    def http_validators(self, url: str) -> tuple[str | None, str | None]:
        row = self.conn.execute("SELECT etag, last_modified FROM http_cache WHERE url=?", (url,)).fetchone()
        return (row["etag"], row["last_modified"]) if row else (None, None)

    def save_http_validators(self, url: str, etag: str | None, last_modified: str | None) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO http_cache (url, etag, last_modified, fetched_at) VALUES (?,?,?,?)",
                      (url, etag, last_modified, _iso(utcnow())))

    # ---- health ---------------------------------------------------------
    def record_run(self, source: str, started_at: datetime, ok: bool, n_items: int, n_new: int,
                   error: str | None = None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO source_runs (source, started_at, ok, n_items, n_new, error) VALUES (?,?,?,?,?,?)",
                      (source, _iso(started_at), int(ok), n_items, n_new, error))

    def source_health(self, last_n: int = 5) -> pd.DataFrame:
        return pd.read_sql_query(
            """SELECT source,
                      COUNT(*) AS runs,
                      SUM(ok) AS ok_runs,
                      SUM(n_items) AS items,
                      SUM(n_new) AS new_items,
                      MAX(started_at) AS last_run,
                      (SELECT error FROM source_runs r2 WHERE r2.source = r.source AND r2.ok = 0
                       ORDER BY id DESC LIMIT 1) AS last_error
               FROM (SELECT * FROM source_runs r1
                     WHERE (SELECT COUNT(*) FROM source_runs r3
                            WHERE r3.source = r1.source AND r3.id > r1.id) < ?) r
               GROUP BY source ORDER BY source""",
            self.conn, params=[last_n],
        )

    def counts(self) -> dict[str, int]:
        return {t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("articles", "mentions", "sentiment", "signals", "prices")}

    # ---- alerts ---------------------------------------------------------
    def alert_already_sent(self, ticker: str, day: str, direction: str) -> bool:
        return self.conn.execute("SELECT 1 FROM alerts_sent WHERE ticker=? AND day=? AND direction=?",
                                 (ticker, day, direction)).fetchone() is not None

    def mark_alert_sent(self, ticker: str, day: str, direction: str) -> None:
        with self.tx() as c:
            c.execute("INSERT OR IGNORE INTO alerts_sent (ticker, day, direction, sent_at) VALUES (?,?,?,?)",
                      (ticker, day, direction, _iso(utcnow())))
