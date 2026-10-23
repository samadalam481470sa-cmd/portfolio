"""eBay connector (Browse API). OFF by default. NOT TESTED against the live API.

This is a starting point for REAL marketplace prices. It needs your own eBay developer
keys. Add them in config.json, then turn it on:

    {"providers": {"ebay": {"enabled": true, "client_id": "...", "client_secret": "..."}}}

How it works: each poll it takes a few real (non-sample) products from the catalog,
searches eBay for each one by brand and name, and records the lowest fixed-price
result as the eBay offer. Matching is by title search, so check the results by hand.
Follow eBay's API terms and rate limits.
"""
import asyncio
import base64

import httpx

from .. import db as dbm
from .base import Batch, OfferRow, Provider

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


class EbayProvider(Provider):
    name = "ebay"
    note = "Real eBay prices through the Browse API. Needs your keys. Untested."

    def __init__(self, cfg, root_cfg):
        self.cfg = cfg
        self.interval = float(cfg.get("poll_seconds", 20))
        self.token = ""
        self.token_until = 0.0
        self.offset = 0

    async def _token(self, client):
        loop = asyncio.get_running_loop()
        if self.token and loop.time() < self.token_until:
            return self.token
        pair = f"{self.cfg['client_id']}:{self.cfg['client_secret']}".encode()
        r = await client.post(
            TOKEN_URL,
            headers={"Authorization": "Basic " + base64.b64encode(pair).decode(),
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials",
                  "scope": "https://api.ebay.com/oauth/api_scope"},
        )
        r.raise_for_status()
        body = r.json()
        self.token = body["access_token"]
        self.token_until = loop.time() + int(body.get("expires_in", 7200)) - 120
        return self.token

    def _next_products(self):
        n = int(self.cfg.get("products_per_poll", 3))
        rows = dbm.rows(
            "SELECT pkey, name, brand, category, upc FROM catalog.products "
            "WHERE is_sample=0 ORDER BY id LIMIT ? OFFSET ?", (n, self.offset))
        self.offset = self.offset + n if len(rows) == n else 0
        return rows

    async def poll(self):
        if not self.cfg.get("client_id") or not self.cfg.get("client_secret"):
            raise RuntimeError("Add client_id and client_secret for eBay in config.json.")
        products = await asyncio.to_thread(self._next_products)
        if not products:
            return None
        batch = Batch()
        async with httpx.AsyncClient(timeout=20) as client:
            token = await self._token(client)
            for p in products:
                r = await client.get(
                    SEARCH_URL,
                    params={"q": f"{p['brand']} {p['name']}".strip(), "limit": 20,
                            "filter": "buyingOptions:{FIXED_PRICE}"},
                    headers={"Authorization": f"Bearer {token}",
                             "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
                )
                r.raise_for_status()
                items = [i for i in r.json().get("itemSummaries", [])
                         if i.get("price", {}).get("currency") == "USD"]
                if not items:
                    continue
                best = min(items, key=lambda i: float(i["price"]["value"]))
                batch.offers.append(OfferRow(
                    source="ebay", name=p["name"], brand=p["brand"], category=p["category"],
                    pkey=p["pkey"], pack_qty=1, price=float(best["price"]["value"]),
                    url=best.get("itemWebUrl", ""), url_kind="direct",
                    seller=(best.get("seller") or {}).get("username", ""),
                ))
        return batch
