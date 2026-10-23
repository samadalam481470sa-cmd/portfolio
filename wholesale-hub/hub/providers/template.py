"""Template for a new data source. Copy this file, rename it, and fill in poll().

Then register it in providers/__init__.py and add its settings to config.json.

Use official APIs, data vendors, or exports you are allowed to use. Respect each
site's terms and rate limits. Live per-second scraping of store websites is not
something the stores allow, and it gets blocked.
"""
from .base import Batch, OfferRow, Provider


class MyProvider(Provider):
    name = "my_source"
    note = "What this source is."

    def __init__(self, cfg, root_cfg):
        self.cfg = cfg
        self.interval = 60.0  # seconds between polls

    async def poll(self):
        batch = Batch()
        # Fetch real data here, then add one OfferRow per product per store:
        batch.offers.append(OfferRow(
            source="samsclub",      # a key from the Sources tab
            name="Paper Napkins 500 ct",
            brand="ExampleBrand",
            category="Paper Goods",
            upc="",                 # best way to match the same product across stores
            product_key="napkins-500",
            pack_qty=500,
            price=9.98,
            url="https://example.com/real-product-link",
            in_stock=True,
        ))
        return batch  # or None when nothing changed
