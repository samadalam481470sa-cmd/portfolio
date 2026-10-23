"""The shape every data provider follows.

A provider produces Batches. The engine saves each Batch, then updates profit,
trend, and popularity numbers. To add a real data source, copy template.py,
fill in poll(), and register it in providers/__init__.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class OfferRow:
    source: str  # a key from the sources table, such as "samsclub"
    name: str
    price: float  # price of ONE pack as listed
    pack_qty: int = 1  # how many units are in that pack
    brand: str = ""
    category: str = "General"
    upc: str = ""
    product_key: str = ""  # any id you use to match the same product across stores
    pkey: str = ""  # a ready-made match key (overrides the three above)
    url: str = ""  # a direct product link when you have one
    url_kind: str = "direct"
    in_stock: bool = True
    seller: str = ""
    sales_rank: int | None = None  # lower is better
    is_sample: bool = False


@dataclass
class Batch:
    offers: list = field(default_factory=list)
    searches: dict = field(default_factory=dict)  # pkey -> searches since the last poll
    search_history: list = field(default_factory=list)  # (pkey, minute_ts, count)
    tick_history: list = field(default_factory=list)  # (pkey, source, ts, unit_price)

    def empty(self):
        return not (self.offers or self.searches or self.search_history or self.tick_history)


class Provider:
    name = "base"
    interval = 1.0  # seconds between polls
    note = ""

    async def start(self):
        """Runs once before the first poll."""

    async def poll(self):
        """Return a Batch, or None when there is nothing new."""
        return None

    async def daily(self):
        """Runs once a day at the refresh hour. Return a Batch or None."""
        return None


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def make_pkey(o):
    """The key that says two offers are the same product.

    Priority: explicit pkey, then UPC, then product_key, then brand plus name.
    """
    if o.pkey:
        return o.pkey
    digits = re.sub(r"\D", "", o.upc or "")
    if digits:
        return "upc:" + digits
    if o.product_key:
        return "key:" + norm(o.product_key)
    return "name:" + norm(f"{o.brand} {o.name}")
