"""The web API and dashboard server."""
import asyncio
import csv
import io
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db as dbm
from . import engine as eng
from .config import CONFIG, STATIC_DIR
from .providers import build as build_providers
from .providers.csv_import import TEMPLATE, log_import, parse_csv, source_lookup
from .sources_seed import seed_sources

log = logging.getLogger("hub.api")
engine = None


@asynccontextmanager
async def lifespan(app):
    global engine
    dbm.init_all()
    with dbm.write() as con:
        seed_sources(con)
    providers = build_providers(CONFIG)
    eng.init_provider_status(providers)
    engine = eng.Engine(providers)
    tasks = engine.start()
    log.info("Wholesale Hub running at http://%s:%s", CONFIG["host"], CONFIG["port"])
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Wholesale Hub", lifespan=lifespan)


# ---------------------------------------------------------------- helpers
def _sources():
    out = {}
    for r in dbm.rows("SELECT * FROM sources.sources"):
        r["how_to_buy"] = json.loads(r["how_to_buy"] or "[]")
        out[r["key"]] = r
    return out


def _like(q):
    return "%" + q.replace("%", "").replace("_", "") + "%"


OPP_SORTS = {"profit": "o.profit", "margin": "o.margin_pct", "roi": "o.roi_pct",
             "trend": "sc.trend_score"}


def _opp_query(q, category, min_profit, min_margin, sort, limit, offset):
    where, params = ["o.profit >= ?", "o.margin_pct >= ?"], [min_profit, min_margin]
    if q:
        where.append("(p.name LIKE ? OR p.brand LIKE ?)")
        params += [_like(q), _like(q)]
    if category:
        where.append("p.category = ?")
        params.append(category)
    order = OPP_SORTS.get(sort, "o.profit")
    sql = f"""
        SELECT o.*, p.name, p.brand, p.category, p.is_sample,
               bs.url AS buy_url, bs.url_kind AS buy_url_kind,
               ss.url AS sell_url, ss.url_kind AS sell_url_kind,
               COALESCE(sc.trend_score, 0) AS trend_score
        FROM opps.opportunities o
        JOIN catalog.products p ON p.id = o.product_id
        JOIN prices.offers bs ON bs.product_id = o.product_id AND bs.source = o.buy_source
        JOIN prices.offers ss ON ss.product_id = o.product_id AND ss.source = o.sell_source
        LEFT JOIN trends.scores sc ON sc.product_id = o.product_id
        WHERE {' AND '.join(where)}
        ORDER BY {order} DESC
        LIMIT ? OFFSET ?"""
    return sql, params + [limit, offset]


# -------------------------------------------------------------- endpoints
@app.get("/api/overview")
def overview():
    sample = dbm.one("SELECT COUNT(*) FROM catalog.products WHERE is_sample=1") or 0
    total = dbm.one("SELECT COUNT(*) FROM catalog.products") or 0
    strong = dbm.one(
        "SELECT COUNT(*) FROM opps.opportunities WHERE profit >= ? AND margin_pct >= ?",
        (CONFIG["alert_min_profit"], CONFIG["alert_min_margin_pct"]),
    ) or 0
    return {
        "products": total,
        "sample_products": sample,
        "sample_mode": sample > 0,
        "offers": dbm.one("SELECT COUNT(*) FROM prices.offers") or 0,
        "opportunities": dbm.one("SELECT COUNT(*) FROM opps.opportunities") or 0,
        "strong_deals": strong,
        "updates_per_min": engine.per_minute() if engine else 0,
        "total_updates": eng.S.total_updates,
        "uptime_s": int(time.time() - eng.S.started),
        "last_daily": eng.get_meta("last_daily", ""),
        "alert_min_profit": CONFIG["alert_min_profit"],
        "alert_min_margin_pct": CONFIG["alert_min_margin_pct"],
    }


@app.get("/api/categories")
def categories():
    return [r["category"] for r in dbm.rows(
        "SELECT DISTINCT category FROM catalog.products ORDER BY category")]


@app.get("/api/sources")
def sources():
    return {"sources": list(_sources().values()),
            "providers": dbm.rows("SELECT * FROM sources.provider_status ORDER BY provider"),
            "imports": dbm.rows("SELECT * FROM sources.import_log ORDER BY id DESC LIMIT 10")}


class SourceUpdate(BaseModel):
    fee_pct: Optional[float] = None
    ship_per_sale: Optional[float] = None
    enabled: Optional[bool] = None
    search_url: Optional[str] = None


@app.post("/api/sources/{key}")
async def update_source(key: str, body: SourceUpdate):
    if key not in _sources():
        raise HTTPException(404, "Unknown source")

    def work():
        with dbm.write() as con:
            if body.fee_pct is not None:
                con.execute("UPDATE sources.sources SET fee_pct=? WHERE key=?", (body.fee_pct, key))
            if body.ship_per_sale is not None:
                con.execute("UPDATE sources.sources SET ship_per_sale=? WHERE key=?",
                            (body.ship_per_sale, key))
            if body.enabled is not None:
                con.execute("UPDATE sources.sources SET enabled=? WHERE key=?",
                            (1 if body.enabled else 0, key))
            if body.search_url is not None:
                con.execute("UPDATE sources.sources SET search_url=? WHERE key=?",
                            (body.search_url, key))
        eng.recompute_all()

    await asyncio.to_thread(work)
    return {"ok": True}


@app.get("/api/opportunities")
def opportunities(q: str = "", category: str = "", min_profit: float = 0.01,
                  min_margin: float = 0.0, sort: str = "profit",
                  limit: int = Query(50, le=500), offset: int = 0):
    sql, params = _opp_query(q, category, min_profit, min_margin, sort, limit, offset)
    return dbm.rows(sql, params)


@app.get("/api/export/opportunities.csv")
def export_opportunities(q: str = "", category: str = "", min_profit: float = 0.01,
                         min_margin: float = 0.0, sort: str = "profit"):
    sql, params = _opp_query(q, category, min_profit, min_margin, sort, 5000, 0)
    src = _sources()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["product", "category", "buy_at", "buy_unit_price", "buy_link", "sell_on",
                "sell_price", "sell_pack_qty", "fees", "shipping", "profit", "margin_pct",
                "roi_pct", "sample_data"])
    for r in dbm.rows(sql, params):
        w.writerow([f"{r['brand']} {r['name']}".strip(), r["category"],
                    src[r["buy_source"]]["name"], r["buy_unit"], r["buy_url"],
                    src[r["sell_source"]]["name"], r["sell_price"], r["sell_pack_qty"],
                    r["fees"], r["ship"], r["profit"], r["margin_pct"], r["roi_pct"],
                    "yes" if r["is_sample"] else "no"])
    return PlainTextResponse(out.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=opportunities.csv"})


def _score_rows(order, where="", limit=50):
    return dbm.rows(f"""
        SELECT p.id, p.name, p.brand, p.category, p.is_sample, s.searches_15m,
               s.searches_prev_45m, s.searches_24h, s.trend_score, s.popularity_score,
               s.best_rank,
               (SELECT MAX(profit) FROM opps.opportunities WHERE product_id = p.id) AS best_profit
        FROM trends.scores s JOIN catalog.products p ON p.id = s.product_id
        {where} ORDER BY {order} DESC LIMIT ?""", (limit,))


@app.get("/api/trending")
def trending(limit: int = Query(50, le=500)):
    return _score_rows("s.trend_score", "WHERE s.searches_15m >= 5", limit)


@app.get("/api/popular")
def popular(limit: int = Query(50, le=500)):
    return _score_rows("s.popularity_score", "", limit)


@app.get("/api/searched")
def searched(limit: int = Query(50, le=500)):
    return _score_rows("s.searches_24h", "", limit)


@app.get("/api/cheapest")
def cheapest(q: str = "", category: str = "", kind: str = "wholesale",
             limit: int = Query(50, le=500)):
    where, params = ["o.in_stock = 1"], []
    if kind in ("wholesale", "marketplace"):
        where.append("s.kind = ?")
        params.append(kind)
    if q:
        where.append("(p.name LIKE ? OR p.brand LIKE ?)")
        params += [_like(q), _like(q)]
    if category:
        where.append("p.category = ?")
        params.append(category)
    sql = f"""
        WITH ranked AS (
          SELECT o.product_id, o.source, o.unit_price, o.price, o.pack_qty, o.url, o.url_kind,
                 ROW_NUMBER() OVER (PARTITION BY o.product_id ORDER BY o.unit_price) AS rn,
                 AVG(o.unit_price) OVER (PARTITION BY o.product_id) AS avg_unit,
                 COUNT(*) OVER (PARTITION BY o.product_id) AS n
          FROM prices.offers o
          JOIN sources.sources s ON s.key = o.source
          JOIN catalog.products p ON p.id = o.product_id
          WHERE {' AND '.join(where)})
        SELECT r.product_id AS id, p.name, p.brand, p.category, p.is_sample, r.source,
               r.unit_price, r.price, r.pack_qty, r.url, r.url_kind, r.n AS stores,
               ROUND((r.avg_unit - r.unit_price) / r.avg_unit * 100, 2) AS below_avg_pct
        FROM ranked r JOIN catalog.products p ON p.id = r.product_id
        WHERE r.rn = 1 AND r.n >= 2
        ORDER BY below_avg_pct DESC LIMIT ?"""
    return dbm.rows(sql, params + [limit])


@app.get("/api/products")
def products(q: str = "", category: str = "", limit: int = Query(50, le=500), offset: int = 0):
    where, params = ["1=1"], []
    if q:
        where.append("(name LIKE ? OR brand LIKE ?)")
        params += [_like(q), _like(q)]
    if category:
        where.append("category = ?")
        params.append(category)
    return dbm.rows(
        f"SELECT id, name, brand, category, is_sample FROM catalog.products "
        f"WHERE {' AND '.join(where)} ORDER BY id LIMIT ? OFFSET ?", params + [limit, offset])


@app.get("/api/products/{pid}")
def product(pid: int):
    p = dbm.rows("SELECT * FROM catalog.products WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "Unknown product")
    src = _sources()
    offers = dbm.rows("SELECT * FROM prices.offers WHERE product_id=? ORDER BY unit_price", (pid,))
    for o in offers:
        o["source_name"] = src[o["source"]]["name"]
        o["kind"] = src[o["source"]]["kind"]
    opps = dbm.rows(
        "SELECT * FROM opps.opportunities WHERE product_id=? ORDER BY profit DESC", (pid,))
    scores = dbm.rows("SELECT * FROM trends.scores WHERE product_id=?", (pid,))
    return {"product": p[0], "offers": offers, "opportunities": opps,
            "scores": scores[0] if scores else None, "sources": src}


@app.get("/api/products/{pid}/history")
def history(pid: int, source: str, hours: int = Query(24, le=24 * 365)):
    since = int(time.time()) - hours * 3600
    if hours <= CONFIG["keep_tick_days"] * 24:
        pts = dbm.rows(
            "SELECT ts, unit_price FROM prices.ticks WHERE product_id=? AND source=? AND ts>=? "
            "ORDER BY ts LIMIT 3000", (pid, source, since))
        return [[r["ts"], r["unit_price"]] for r in pts]
    pts = dbm.rows(
        "SELECT CAST(strftime('%s', day) AS INTEGER) ts, close unit_price FROM prices.daily "
        "WHERE product_id=? AND source=? AND CAST(strftime('%s', day) AS INTEGER)>=? ORDER BY day",
        (pid, source, since))
    return [[r["ts"], r["unit_price"]] for r in pts]


@app.get("/api/alerts")
def alerts(limit: int = Query(30, le=200)):
    return dbm.rows(
        "SELECT a.*, p.name, p.brand, p.is_sample FROM opps.alerts a "
        "JOIN catalog.products p ON p.id = a.product_id WHERE p.is_sample = 0 "
        "ORDER BY a.id DESC LIMIT ?", (limit,))


@app.get("/api/health")
def health():
    return {"ok": True, "providers": dbm.rows("SELECT * FROM sources.provider_status")}


@app.get("/api/import/template.csv")
def import_template():
    return PlainTextResponse(TEMPLATE, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=import-template.csv"})


@app.post("/api/import/csv")
async def import_csv(request: Request):
    text = (await request.body()).decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise HTTPException(400, "The file is empty.")

    def work():
        offers, bad, errors = parse_csv(text, source_lookup())
        return offers, bad, errors

    offers, bad, errors = await asyncio.to_thread(work)
    res = None
    if offers:
        from .providers.base import Batch
        res = await asyncio.to_thread(eng.ingest, "csv_import", Batch(offers=offers))
        engine.after_ingest(res)
    await asyncio.to_thread(log_import, "upload", len(offers), bad, "; ".join(errors))
    return {"imported": len(offers), "bad_rows": bad, "errors": errors}


@app.post("/api/admin/refresh")
async def admin_refresh():
    asyncio.get_running_loop().create_task(engine.run_daily())
    return {"ok": True, "message": "Daily refresh started."}


@app.get("/api/stream")
async def stream(request: Request):
    q = engine.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            engine.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
