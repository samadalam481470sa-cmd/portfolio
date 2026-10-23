"""The engine: saves provider data, works out profit and trend numbers, and runs the
background loops (live polling, score updates, and the daily refresh).

Profit math for one buy-here, sell-there pair:

    cost    = buy unit price x units in the marketplace pack
    fees    = marketplace price x marketplace fee %
    profit  = marketplace price - fees - shipping per sale - cost
    margin  = profit / marketplace price
    roi     = profit / cost

Only pairs with profit above zero are stored.
"""
import asyncio
import datetime
import logging
import threading
import time
from collections import deque

from . import db as dbm
from .config import CONFIG
from .links import search_url
from .providers.base import make_pkey

log = logging.getLogger("hub.engine")


class State:
    def __init__(self):
        self.product_cache = {}  # pkey -> (id, name)
        self.sources = {}
        self.sources_at = 0.0
        self.total_updates = 0
        self.recent = deque()  # (timestamp, updates)
        self.lock = threading.Lock()
        self.started = time.time()


S = State()


# ---------------------------------------------------------------- helpers
def load_sources(con, force=False):
    if force or time.time() - S.sources_at > 20:
        rows = con.execute("SELECT * FROM sources.sources").fetchall()
        S.sources = {r["key"]: dict(r) for r in rows}
        S.sources_at = time.time()
    return S.sources


def get_meta(key, default=""):
    v = dbm.one("SELECT value FROM sources.meta WHERE key=?", (key,))
    return default if v is None else v


def set_meta(key, value):
    with dbm.write() as con:
        con.execute(
            "INSERT INTO sources.meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def resolve_product(con, o, now):
    pkey = make_pkey(o)
    hit = S.product_cache.get(pkey)
    if hit:
        return hit[0]
    row = con.execute("SELECT id, name FROM catalog.products WHERE pkey=?", (pkey,)).fetchone()
    if row:
        pid, name = row["id"], row["name"]
    else:
        cur = con.execute(
            "INSERT INTO catalog.products(pkey,name,brand,category,upc,is_sample,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (pkey, o.name, o.brand, o.category or "General", o.upc or "", 1 if o.is_sample else 0, now),
        )
        pid, name = cur.lastrowid, o.name
    S.product_cache[pkey] = (pid, name)
    return pid


def lookup_pid(con, pkey):
    hit = S.product_cache.get(pkey)
    if hit:
        return hit[0]
    row = con.execute("SELECT id, name FROM catalog.products WHERE pkey=?", (pkey,)).fetchone()
    if row:
        S.product_cache[pkey] = (row["id"], row["name"])
        return row["id"]
    return None


UPSERT_OFFER = """
INSERT INTO prices.offers
 (product_id,source,price,pack_qty,unit_price,in_stock,url,url_kind,seller,is_sample,updated_at)
VALUES(?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(product_id,source) DO UPDATE SET
 price=excluded.price, pack_qty=excluded.pack_qty, unit_price=excluded.unit_price,
 in_stock=excluded.in_stock, url=excluded.url, url_kind=excluded.url_kind,
 seller=excluded.seller, is_sample=excluded.is_sample, updated_at=excluded.updated_at
"""


# ---------------------------------------------------------------- ingest
def ingest(provider, batch):
    """Save one Batch. Returns a summary used for the live feed."""
    now = int(time.time())
    minute = now // 60 * 60
    events, affected, updates = [], set(), 0
    with dbm.write() as con:
        src = load_sources(con)
        for o in batch.offers:
            s = src.get(o.source)
            if not s or o.price is None or o.price <= 0 or o.pack_qty <= 0:
                continue
            pid = resolve_product(con, o, now)
            unit = round(o.price / o.pack_qty, 6)
            url, kind = o.url, (o.url_kind if o.url else "search")
            if not url:
                url = search_url(s["search_url"], f"{o.brand} {o.name}".strip())
                kind = "search"
            prev = con.execute(
                "SELECT unit_price, in_stock FROM prices.offers WHERE product_id=? AND source=?",
                (pid, o.source),
            ).fetchone()
            con.execute(
                UPSERT_OFFER,
                (pid, o.source, o.price, o.pack_qty, unit, 1 if o.in_stock else 0, url, kind,
                 o.seller or "", 1 if o.is_sample else 0, now),
            )
            price_changed = prev is None or abs(prev["unit_price"] - unit) > 1e-9
            if price_changed:
                con.execute("INSERT INTO prices.ticks VALUES(?,?,?,?)", (pid, o.source, now, unit))
            if price_changed or bool(prev["in_stock"]) != bool(o.in_stock):
                affected.add(pid)
                updates += 1
            if prev is not None and price_changed and prev["unit_price"] > 0:
                events.append({
                    "type": "price",
                    "pid": pid,
                    "name": f"{o.brand} {o.name}".strip(),
                    "source": o.source,
                    "source_name": s["name"],
                    "old": prev["unit_price"],
                    "new": unit,
                    "pct": round((unit - prev["unit_price"]) / prev["unit_price"] * 100, 2),
                    "ts": now,
                })
            if o.sales_rank:
                con.execute(
                    "INSERT INTO trends.sales_signals(product_id,source,sales_rank,updated_at) "
                    "VALUES(?,?,?,?) ON CONFLICT(product_id,source) DO UPDATE SET "
                    "sales_rank=excluded.sales_rank, updated_at=excluded.updated_at",
                    (pid, o.source, int(o.sales_rank), now),
                )

        tick_rows = []
        for pkey, source, ts, unit in batch.tick_history:
            pid = lookup_pid(con, pkey)
            if pid is not None:
                tick_rows.append((pid, source, int(ts), float(unit)))
        if tick_rows:
            con.executemany("INSERT INTO prices.ticks VALUES(?,?,?,?)", tick_rows)

        bucket_sql = (
            "INSERT INTO trends.search_buckets(product_id,minute,searches) VALUES(?,?,?) "
            "ON CONFLICT(product_id,minute) DO UPDATE SET searches=searches+excluded.searches"
        )
        hist = []
        for pkey, m, count in batch.search_history:
            pid = lookup_pid(con, pkey)
            if pid is not None and count > 0:
                hist.append((pid, int(m) // 60 * 60, int(count)))
        if hist:
            con.executemany(bucket_sql, hist)
        live = []
        for pkey, count in batch.searches.items():
            pid = lookup_pid(con, pkey)
            if pid is not None and count > 0:
                live.append((pid, minute, int(count)))
        if live:
            con.executemany(bucket_sql, live)

        alerts = recompute_opps(con, affected, now)

        con.execute(
            "INSERT INTO sources.provider_status(provider,enabled,last_run,last_ok,last_error,rows_total) "
            "VALUES(?,1,?,?,'',?) ON CONFLICT(provider) DO UPDATE SET "
            "last_run=excluded.last_run,last_ok=excluded.last_ok,last_error='',"
            "rows_total=rows_total+excluded.rows_total",
            (provider, now, now, len(batch.offers)),
        )
    events.sort(key=lambda e: abs(e["pct"]), reverse=True)
    return {"updates": updates, "events": events[:12], "alerts": alerts, "rows": len(batch.offers)}


def mark_error(provider, message):
    now = int(time.time())
    with dbm.write() as con:
        con.execute(
            "INSERT INTO sources.provider_status(provider,enabled,last_run,last_error) "
            "VALUES(?,1,?,?) ON CONFLICT(provider) DO UPDATE SET last_run=excluded.last_run,"
            "last_error=excluded.last_error",
            (provider, now, str(message)[:300]),
        )


def init_provider_status(providers):
    with dbm.write() as con:
        for p in providers:
            con.execute(
                "INSERT INTO sources.provider_status(provider,enabled,note) VALUES(?,1,?) "
                "ON CONFLICT(provider) DO UPDATE SET enabled=1, note=excluded.note",
                (p.name, p.note),
            )


# ------------------------------------------------------------ opportunities
def recompute_opps(con, pids, now):
    alerts = []
    if not pids:
        return alerts
    src = load_sources(con)
    min_profit = CONFIG["alert_min_profit"]
    min_margin = CONFIG["alert_min_margin_pct"]
    for pid in pids:
        rows = con.execute(
            "SELECT source, price, pack_qty, unit_price FROM prices.offers "
            "WHERE product_id=? AND in_stock=1",
            (pid,),
        ).fetchall()
        old = {
            (r["buy_source"], r["sell_source"]): r["profit"]
            for r in con.execute(
                "SELECT buy_source, sell_source, profit FROM opps.opportunities WHERE product_id=?",
                (pid,),
            )
        }
        con.execute("DELETE FROM opps.opportunities WHERE product_id=?", (pid,))
        buys = [r for r in rows if src.get(r["source"], {}).get("kind") == "wholesale"
                and src[r["source"]]["enabled"]]
        sells = [r for r in rows if src.get(r["source"], {}).get("kind") == "marketplace"
                 and src[r["source"]]["enabled"]]
        for b in buys:
            for s in sells:
                sc = src[s["source"]]
                cost = b["price"] / b["pack_qty"] * s["pack_qty"]
                fees = s["price"] * sc["fee_pct"] / 100.0
                ship = sc["ship_per_sale"]
                profit = s["price"] - fees - ship - cost
                if profit <= 0:
                    continue
                margin = profit / s["price"] * 100.0
                roi = profit / cost * 100.0 if cost > 0 else 0.0
                con.execute(
                    "INSERT INTO opps.opportunities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, b["source"], s["source"], b["unit_price"], b["pack_qty"], s["price"],
                     s["pack_qty"], round(cost, 4), round(fees, 4), ship, round(profit, 4),
                     round(margin, 2), round(roi, 2), round(b["pack_qty"] / s["pack_qty"], 3), now),
                )
                key = (b["source"], s["source"])
                if profit >= min_profit and margin >= min_margin and old.get(key, 0) < min_profit:
                    con.execute(
                        "INSERT INTO opps.alerts(ts,product_id,buy_source,sell_source,profit,margin_pct) "
                        "VALUES(?,?,?,?,?,?)",
                        (now, pid, b["source"], s["source"], round(profit, 4), round(margin, 2)),
                    )
                    name = con.execute(
                        "SELECT brand, name FROM catalog.products WHERE id=?", (pid,)
                    ).fetchone()
                    alerts.append({
                        "type": "deal",
                        "pid": pid,
                        "name": f"{name['brand']} {name['name']}".strip(),
                        "buy_source": b["source"],
                        "buy_name": src[b["source"]]["name"],
                        "sell_source": s["source"],
                        "sell_name": sc["name"],
                        "profit": round(profit, 2),
                        "margin_pct": round(margin, 1),
                        "ts": now,
                    })
    return alerts


def recompute_all():
    """Recalculate every opportunity. Runs after fee changes and in the daily job."""
    ids = [r[0] for r in dbm.db().execute("SELECT id FROM catalog.products").fetchall()]
    now = int(time.time())
    with dbm.write() as con:
        load_sources(con, force=True)
    for i in range(0, len(ids), 500):
        with dbm.write() as con:
            recompute_opps(con, ids[i:i + 500], now)


# ------------------------------------------------------------------ scores
def update_scores():
    """Trend and popularity scores.

    trend      = (searches per minute in the last 15 min - per minute in the 45 min before)
                 / (per minute in the 45 min before + 1)
    popularity = 70% searches in 24 h (against the busiest product)
                 + 30% best sales rank on any marketplace
    """
    now = int(time.time())
    m15 = (now - 15 * 60) // 60 * 60
    m60 = (now - 60 * 60) // 60 * 60
    m24 = (now - 24 * 3600) // 60 * 60
    con = dbm.db()
    rows = con.execute(
        "SELECT product_id, "
        "SUM(CASE WHEN minute >= ? THEN searches ELSE 0 END) s15, "
        "SUM(CASE WHEN minute < ? AND minute >= ? THEN searches ELSE 0 END) s45, "
        "SUM(searches) s24 FROM trends.search_buckets WHERE minute >= ? GROUP BY product_id",
        (m15, m15, m60, m24),
    ).fetchall()
    ranks = {
        r["product_id"]: r["best"]
        for r in con.execute(
            "SELECT product_id, MIN(sales_rank) best FROM trends.sales_signals "
            "WHERE sales_rank IS NOT NULL GROUP BY product_id"
        )
    }
    max24 = max([r["s24"] for r in rows] or [1]) or 1
    out = []
    for r in rows:
        rate_new = r["s15"] / 15.0
        rate_old = r["s45"] / 45.0
        trend = (rate_new - rate_old) / (rate_old + 1.0)
        rank = ranks.get(r["product_id"])
        rank_part = 1.0 / (1.0 + rank / 50.0) if rank else 0.0
        pop = 0.7 * (r["s24"] / max24) + 0.3 * rank_part
        out.append((r["product_id"], r["s15"], r["s45"], r["s24"], round(trend, 4),
                    round(pop, 4), rank, now))
    with dbm.write() as w:
        w.execute("DELETE FROM trends.scores")
        w.executemany("INSERT INTO trends.scores VALUES(?,?,?,?,?,?,?,?)", out)


# ------------------------------------------------------------------- daily
def daily_maintenance():
    """Roll old price ticks into daily summaries, delete old rows, shrink files."""
    now = int(time.time())
    day_start = now // 86400 * 86400
    keep_ticks = day_start - CONFIG["keep_tick_days"] * 86400
    keep_search = now - CONFIG["keep_search_days"] * 86400
    with dbm.write() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO prices.daily(product_id, source, day, lo, hi, avg, close)
            WITH t AS (
              SELECT product_id, source, date(ts,'unixepoch') d, unit_price,
                     ROW_NUMBER() OVER (
                       PARTITION BY product_id, source, date(ts,'unixepoch') ORDER BY ts DESC) rn
              FROM prices.ticks WHERE ts < ?)
            SELECT product_id, source, d, MIN(unit_price), MAX(unit_price), AVG(unit_price),
                   MAX(CASE WHEN rn=1 THEN unit_price END)
            FROM t GROUP BY product_id, source, d
            """,
            (day_start,),
        )
        con.execute("DELETE FROM prices.ticks WHERE ts < ?", (keep_ticks,))
        con.execute("DELETE FROM trends.search_buckets WHERE minute < ?", (keep_search,))
        con.execute("DELETE FROM opps.alerts WHERE ts < ?", (keep_search,))
    con = dbm.db()
    for name in dbm.NAMES:
        try:
            con.execute(f"PRAGMA {name}.wal_checkpoint(TRUNCATE)")
        except Exception:
            pass


# ------------------------------------------------------------------ engine
class Engine:
    def __init__(self, providers):
        self.providers = providers
        self.subs = set()
        self.tasks = []
        self.running_daily = False

    # live stream to dashboards
    def subscribe(self):
        q = asyncio.Queue(maxsize=300)
        self.subs.add(q)
        return q

    def unsubscribe(self, q):
        self.subs.discard(q)

    def publish(self, event):
        for q in list(self.subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def per_minute(self):
        cutoff = time.time() - 60
        with S.lock:
            while S.recent and S.recent[0][0] < cutoff:
                S.recent.popleft()
            return sum(n for _, n in S.recent)

    def after_ingest(self, res):
        if not res:
            return
        if res["updates"]:
            with S.lock:
                S.total_updates += res["updates"]
                S.recent.append((time.time(), res["updates"]))
        if res["events"] or res["alerts"]:
            self.publish({"type": "events", "events": res["events"], "alerts": res["alerts"]})

    # loops
    async def stats_loop(self):
        while True:
            self.publish({"type": "stats", "ts": int(time.time()),
                          "per_min": self.per_minute(), "total": S.total_updates})
            await asyncio.sleep(1)

    async def provider_loop(self, p):
        try:
            await p.start()
        except Exception as e:
            log.exception("provider %s failed to start", p.name)
            await asyncio.to_thread(mark_error, p.name, e)
        while True:
            t0 = time.monotonic()
            try:
                batch = await p.poll()
                if batch is not None and not batch.empty():
                    self.after_ingest(await asyncio.to_thread(ingest, p.name, batch))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("provider %s poll failed", p.name)
                await asyncio.to_thread(mark_error, p.name, e)
                await asyncio.sleep(5)
            await asyncio.sleep(max(0.05, p.interval - (time.monotonic() - t0)))

    async def scores_loop(self):
        while True:
            try:
                await asyncio.to_thread(update_scores)
            except Exception:
                log.exception("score update failed")
            await asyncio.sleep(CONFIG["scores_seconds"])

    async def daily_loop(self):
        while True:
            await asyncio.sleep(30)
            now = datetime.datetime.now()
            today = now.strftime("%Y-%m-%d")
            if now.hour >= CONFIG["daily_refresh_hour"] and get_meta("last_daily") != today:
                await self.run_daily()

    async def run_daily(self):
        if self.running_daily:
            return
        self.running_daily = True
        try:
            await asyncio.to_thread(set_meta, "last_daily", datetime.date.today().isoformat())
            for p in self.providers:
                try:
                    batch = await p.daily()
                    if batch is not None and not batch.empty():
                        self.after_ingest(await asyncio.to_thread(ingest, p.name, batch))
                except Exception as e:
                    log.exception("daily refresh failed for %s", p.name)
                    await asyncio.to_thread(mark_error, p.name, e)
            await asyncio.to_thread(daily_maintenance)
            await asyncio.to_thread(recompute_all)
            await asyncio.to_thread(update_scores)
            await asyncio.to_thread(set_meta, "last_daily_done", int(time.time()))
            self.publish({"type": "note", "text": "Daily refresh finished."})
        finally:
            self.running_daily = False

    def start(self):
        loop = asyncio.get_running_loop()
        self.tasks = [
            loop.create_task(self.stats_loop()),
            loop.create_task(self.scores_loop()),
            loop.create_task(self.daily_loop()),
        ] + [loop.create_task(self.provider_loop(p)) for p in self.providers]
        return self.tasks
