"""Demo provider: SIMULATED data so the dashboard works the moment you start it.

Everything this provider makes is marked SAMPLE. Prices, packs, searches, and ranks
are invented. They are NOT real store prices. The brands are made up too. Turn this
provider off in config.json when you load real data:

    {"providers": {"demo": {"enabled": false}}}
"""
import math
import random
import time

from ..db import db as get_db
from .base import Batch, OfferRow, Provider

BRANDS = ["Northfield", "Kestrel", "Maple & Oak", "Brightway", "Harbor Lane", "Summit Co"]

# category, item, typical wholesale pack size (units), wholesale price per unit in USD
ITEMS = [
    ("Paper Goods", "Paper Napkins", 500, 0.020),
    ("Paper Goods", "Paper Towels", 12, 1.10),
    ("Paper Goods", "Toilet Paper", 30, 0.65),
    ("Paper Goods", "Facial Tissue", 6, 1.40),
    ("Paper Goods", "Paper Plates", 300, 0.045),
    ("Paper Goods", "Paper Cups", 200, 0.060),
    ("Paper Goods", "Copy Paper", 5, 5.20),
    ("Cleaning", "Trash Bags", 100, 0.120),
    ("Cleaning", "Dish Soap", 4, 2.40),
    ("Cleaning", "Laundry Pods", 150, 0.220),
    ("Cleaning", "Disinfecting Wipes", 6, 3.20),
    ("Cleaning", "All-Purpose Cleaner", 3, 3.80),
    ("Cleaning", "Sponges", 20, 0.450),
    ("Cleaning", "Hand Soap", 6, 1.90),
    ("Kitchen", "Aluminum Foil", 3, 6.50),
    ("Kitchen", "Zip Bags", 300, 0.060),
    ("Kitchen", "Plastic Wrap", 2, 5.50),
    ("Kitchen", "Disposable Gloves", 200, 0.090),
    ("Kitchen", "Food Storage Containers", 3, 5.60),
    ("Pantry", "Bottled Water", 40, 0.180),
    ("Pantry", "Coffee Pods", 72, 0.550),
    ("Pantry", "Granola Bars", 48, 0.550),
    ("Pantry", "Protein Bars", 18, 1.350),
    ("Pantry", "Olive Oil", 2, 11.00),
    ("Pantry", "White Rice", 2, 8.00),
    ("Pantry", "Pasta", 6, 1.250),
    ("Pantry", "Canned Tuna", 12, 1.000),
    ("Pantry", "Peanut Butter", 2, 4.50),
    ("Pantry", "Snack Chips", 20, 0.750),
    ("Office", "Ballpoint Pens", 60, 0.140),
    ("Office", "Sticky Notes", 24, 0.650),
    ("Office", "Markers", 24, 0.550),
    ("Office", "AA Batteries", 48, 0.450),
    ("Office", "AAA Batteries", 36, 0.500),
    ("Health and Beauty", "Shampoo", 2, 6.00),
    ("Health and Beauty", "Body Wash", 3, 4.50),
    ("Health and Beauty", "Razor Refills", 16, 1.100),
    ("Health and Beauty", "Sunscreen", 2, 7.50),
    ("Health and Beauty", "Toothpaste", 5, 2.200),
    ("Health and Beauty", "Cotton Swabs", 1000, 0.004),
    ("Baby and Pet", "Baby Wipes", 10, 2.40),
    ("Baby and Pet", "Diapers", 200, 0.280),
    ("Baby and Pet", "Cat Litter", 2, 11.00),
    ("Baby and Pet", "Dog Treats", 2, 9.00),
    ("Baby and Pet", "Pet Waste Bags", 300, 0.030),
    ("Home", "LED Light Bulbs", 16, 1.200),
    ("Home", "Phone Charging Cables", 3, 4.50),
    ("Home", "Extension Cords", 3, 5.50),
]

WHOLESALE = [("samsclub", 1.00), ("costco", 0.97), ("bjs", 1.04), ("webstaurant", 1.12)]
MARKETPLACES = ["walmart", "amazon", "ebay"]


class DemoProvider(Provider):
    name = "demo"
    note = "SAMPLE DATA. Simulated prices. Not real store prices."

    def __init__(self, cfg, root_cfg):
        self.cfg = cfg
        self.interval = float(root_cfg.get("tick_seconds", 1.0))
        self.rng = random.Random()
        self.tickn = 0
        self.first = True
        self.bootstrap = False
        self.hot = set()
        self.products = []
        self._build()

    # ---- the simulated world (same every run, so products keep their ids)
    def _build(self):
        rng = random.Random(7)
        count = int(self.cfg.get("product_count", 120))
        for i in range(count):
            cat, item, pack, unit = ITEMS[i % len(ITEMS)]
            bi = (i // len(ITEMS)) % len(BRANDS)
            variant = i // (len(ITEMS) * len(BRANDS))
            mult = 0.85 + 0.06 * bi
            p = {
                "pkey": f"demo:{i}",
                "name": item + (f" Style {variant + 1}" if variant else ""),
                "brand": BRANDS[bi],
                "category": cat,
                "weight": rng.lognormvariate(0, 0.9),
                "offers": {},
            }
            for src, smult in rng.sample(WHOLESALE, rng.randint(1, 3)):
                wpack = pack * rng.choice([1, 1, 2])
                wunit = unit * mult * smult * (1 + rng.uniform(-0.04, 0.04))
                price = max(round(wunit * wpack, 2), 0.5)
                p["offers"][src] = {"kind": "wholesale", "pack": wpack, "price": price,
                                    "anchor": price, "stock": True, "rank": None}
            for src in rng.sample(MARKETPLACES, rng.randint(1, 3)):
                mpack = max(1, int(pack * rng.choice([0.5, 1, 1, 2])))
                price = max(round(unit * mult * mpack * rng.uniform(0.95, 2.4), 2), 0.99)
                p["offers"][src] = {"kind": "marketplace", "pack": mpack, "price": price,
                                    "anchor": price, "stock": True,
                                    "rank": max(1, int(2000 / p["weight"] + rng.uniform(0, 300)))}
            self.products.append(p)
        self.hot = {p["pkey"] for p in self.rng.sample(self.products, min(6, len(self.products)))}

    def _row(self, p, src, o):
        return OfferRow(
            source=src, name=p["name"], brand=p["brand"], category=p["category"],
            pack_qty=o["pack"], price=o["price"], in_stock=o["stock"], pkey=p["pkey"],
            is_sample=True, seller="SAMPLE", sales_rank=o["rank"],
        )

    async def start(self):
        con = get_db()
        try:
            have = con.execute(
                "SELECT COUNT(*) FROM catalog.products WHERE is_sample=1"
            ).fetchone()[0]
        except Exception:
            have = 0
        self.bootstrap = have == 0

    def _history(self, now):
        ticks, searches = [], []
        rng = random.Random(11)
        limit = min(len(self.products), 300)
        for p in self.products[:limit]:
            for src, o in p["offers"].items():
                x = o["price"] / o["pack"]
                for step in range(48):
                    ticks.append((p["pkey"], src, now - step * 1800, round(x, 4)))
                    x *= 1 + rng.gauss(0, 0.01)
        total_w = sum(p["weight"] for p in self.products) or 1.0
        per_min = self.cfg.get("searches_per_tick", 40) * 60.0
        now_min = now // 60 * 60
        for p in self.products[:limit]:
            r = per_min * p["weight"] / total_w
            for m in range(60):
                rate = r * (4.0 if (p["pkey"] in self.hot and m < 15) else 1.0)
                c = max(0, int(round(rng.gauss(rate, math.sqrt(max(rate, 0.1))))))
                searches.append((p["pkey"], now_min - m * 60, c))
            for h in range(1, 24):
                c = max(0, int(round(rng.gauss(r * 60, math.sqrt(max(r * 60, 1))))))
                searches.append((p["pkey"], now_min - h * 3600, c))
        return ticks, searches

    def _full(self, with_history):
        batch = Batch()
        for p in self.products:
            for src, o in p["offers"].items():
                batch.offers.append(self._row(p, src, o))
        if with_history:
            batch.tick_history, batch.search_history = self._history(int(time.time()))
        return batch

    def _tick(self):
        rnd = self.rng
        batch = Batch()
        if not self.products:
            return batch
        for _ in range(int(self.cfg.get("updates_per_tick", 25))):
            p = rnd.choice(self.products)
            src = rnd.choice(list(p["offers"]))
            o = p["offers"][src]
            mult = 1 + rnd.gauss(0, 0.004)
            if o["kind"] == "wholesale" and rnd.random() < 0.01:
                mult = rnd.uniform(0.88, 0.95)  # a brief sale at the wholesale store
            price = o["price"] * mult + (o["anchor"] - o["price"]) * 0.15
            price = min(max(price, o["anchor"] * 0.7), o["anchor"] * 1.3)
            o["price"] = max(round(price, 2), 0.5)
            if rnd.random() < 0.003:
                o["stock"] = not o["stock"]
            if o["rank"]:
                o["rank"] = max(1, int(o["rank"] * (1 + rnd.gauss(0, 0.01))))
            batch.offers.append(self._row(p, src, o))
        self.tickn += 1
        if self.tickn % 120 == 1:
            self.hot = {p["pkey"] for p in rnd.sample(self.products, min(6, len(self.products)))}
        weights = [p["weight"] * (5.0 if p["pkey"] in self.hot else 1.0) for p in self.products]
        picks = rnd.choices(self.products, weights=weights,
                            k=int(self.cfg.get("searches_per_tick", 40)))
        for p in picks:
            batch.searches[p["pkey"]] = batch.searches.get(p["pkey"], 0) + 1
        return batch

    async def poll(self):
        if self.first:
            self.first = False
            return self._full(self.bootstrap)
        return self._tick()

    async def daily(self):
        return self._full(False)
