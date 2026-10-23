"""CSV import: the way to load REAL prices.

Drop a CSV file into the imports folder (or upload one on the Import tab). Each row is
one offer: one product, at one store, at one price.

Columns (names are flexible, see ALIASES). Required: source, name, price.

    source        a store key or name from the Sources tab (samsclub, Costco, Walmart ...)
    name          product name
    price         price of one pack as listed at that store
    pack_qty      units in that pack (default 1)
    brand, category
    upc           barcode. Best way to match the same product across stores.
    product_key   any id you use to match products when there is no UPC
    url           direct product link
    in_stock      1 or 0 (default 1)
    sales_rank    marketplace sales rank, lower is better
"""
import asyncio
import csv
import io
import shutil
import time

from .. import db as dbm
from ..config import CONFIG, IMPORT_DIR
from .base import Batch, OfferRow, Provider

ALIASES = {
    "source": ["source", "store", "site", "marketplace", "vendor"],
    "name": ["name", "product_name", "title", "product"],
    "brand": ["brand"],
    "category": ["category", "department"],
    "upc": ["upc", "gtin", "ean", "barcode"],
    "product_key": ["product_key", "sku", "key", "model", "item_number"],
    "pack_qty": ["pack_qty", "pack", "qty", "quantity", "units", "count"],
    "price": ["price", "pack_price", "cost"],
    "url": ["url", "link"],
    "in_stock": ["in_stock", "stock", "available"],
    "sales_rank": ["sales_rank", "rank"],
    "seller": ["seller"],
}

TEMPLATE = (
    "source,name,brand,category,upc,product_key,pack_qty,price,url,in_stock,sales_rank\n"
    "samsclub,Paper Napkins 500 ct,ExampleBrand,Paper Goods,,napkins-500,500,9.98,"
    "https://example.com/replace-with-real-link,1,\n"
    "walmart,Paper Napkins 500 ct,ExampleBrand,Paper Goods,,napkins-500,500,14.99,"
    "https://example.com/replace-with-real-link,1,1200\n"
)


def source_lookup():
    """Map lowercase store keys and names to store keys."""
    lookup = {}
    for r in dbm.rows("SELECT key, name FROM sources.sources"):
        lookup[r["key"].lower()] = r["key"]
        lookup[r["name"].lower()] = r["key"]
    return lookup


def _pick(row, field):
    for alias in ALIASES[field]:
        v = row.get(alias)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def _number(text):
    return float(str(text).replace("$", "").replace(",", "").strip())


def parse_csv(text, lookup):
    """Returns (offers, bad_row_count, first_errors)."""
    offers, errors, bad = [], [], 0
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames:
        reader.fieldnames = [f.strip().lower().replace(" ", "_") for f in reader.fieldnames]
    for n, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower().replace(" ", "_"): v for k, v in raw.items()}
        try:
            src = lookup.get(_pick(row, "source").lower())
            if not src:
                raise ValueError(f"unknown source '{_pick(row, 'source')}'")
            name = _pick(row, "name")
            if not name:
                raise ValueError("missing name")
            price = _number(_pick(row, "price"))
            if price <= 0:
                raise ValueError("price must be above zero")
            pack = int(float(_pick(row, "pack_qty") or 1))
            if pack < 1:
                raise ValueError("pack_qty must be at least 1")
            stock_text = _pick(row, "in_stock").lower()
            in_stock = stock_text not in ("0", "false", "no", "n", "out", "out of stock")
            rank_text = _pick(row, "sales_rank")
            url = _pick(row, "url")
            offers.append(OfferRow(
                source=src, name=name, price=price, pack_qty=pack,
                brand=_pick(row, "brand"), category=_pick(row, "category") or "General",
                upc=_pick(row, "upc"), product_key=_pick(row, "product_key"),
                url=url if url.lower().startswith("http") else "", url_kind="direct",
                in_stock=in_stock, seller=_pick(row, "seller"),
                sales_rank=int(float(rank_text)) if rank_text else None,
            ))
        except Exception as e:
            bad += 1
            if len(errors) < 5:
                errors.append(f"line {n}: {e}")
    return offers, bad, errors


def log_import(filename, ok, bad, message):
    with dbm.write() as con:
        con.execute(
            "INSERT INTO sources.import_log(ts,filename,rows_ok,rows_bad,message) VALUES(?,?,?,?,?)",
            (int(time.time()), filename, ok, bad, message[:500]),
        )


class CsvImportProvider(Provider):
    name = "csv_import"
    note = "Reads CSV files from the imports folder."

    def __init__(self, cfg, root_cfg):
        self.interval = float(cfg.get("scan_seconds", 10))

    def _scan(self):
        IMPORT_DIR.mkdir(parents=True, exist_ok=True)
        done = IMPORT_DIR / "done"
        files = sorted(p for p in IMPORT_DIR.glob("*.csv") if p.is_file())
        if not files:
            return None
        lookup = source_lookup()
        batch = Batch()
        for f in files:
            try:
                offers, bad, errors = parse_csv(f.read_text(encoding="utf-8-sig"), lookup)
                batch.offers.extend(offers)
                log_import(f.name, len(offers), bad, "; ".join(errors))
            except Exception as e:
                log_import(f.name, 0, 0, f"could not read file: {e}")
            done.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(done / f"{int(time.time())}-{f.name}"))
        return batch

    async def poll(self):
        return await asyncio.to_thread(self._scan)
