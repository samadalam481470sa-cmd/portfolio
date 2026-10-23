"""Stores the hub knows about at the start.

kind "wholesale"   = where you buy in bulk.
kind "marketplace" = where you resell.

fee_pct and ship_per_sale are ESTIMATES. Replace them with your real numbers on the
"Sources and fees" tab. Fee rates, membership rules, and search links change over
time, so check each store's current terms. These rows are only written the first
time, so your edits are never overwritten.
"""
import json

COMMON_BUY_STEPS = [
    "Open the link and find the exact item. Check the pack size and the price per unit.",
    "Choose shipping or pickup. Check delivery fees and any limit per order.",
    "Keep every invoice. You need them for returns, taxes, and brand approval on some marketplaces.",
    "Check the brand's resale rules before you list the item anywhere.",
]

SEED = [
    {
        "key": "samsclub",
        "name": "Sam's Club",
        "kind": "wholesale",
        "fee_pct": 0,
        "ship_per_sale": 0,
        "search_url": "https://www.samsclub.com/s/{q}",
        "membership": "Membership required. A business membership is available.",
        "how_to_buy": ["Sign in with a membership. Business membership is available."] + COMMON_BUY_STEPS,
    },
    {
        "key": "costco",
        "name": "Costco",
        "kind": "wholesale",
        "fee_pct": 0,
        "ship_per_sale": 0,
        "search_url": "https://www.costco.com/CatalogSearch?keyword={q}",
        "membership": "Membership required. A business membership is available.",
        "how_to_buy": ["Sign in with a membership. Business membership is available."] + COMMON_BUY_STEPS,
    },
    {
        "key": "bjs",
        "name": "BJ's Wholesale",
        "kind": "wholesale",
        "fee_pct": 0,
        "ship_per_sale": 0,
        "search_url": "https://www.bjs.com/search/{q}",
        "membership": "Membership required.",
        "how_to_buy": ["Sign in with a membership."] + COMMON_BUY_STEPS,
    },
    {
        "key": "webstaurant",
        "name": "WebstaurantStore",
        "kind": "wholesale",
        "fee_pct": 0,
        "ship_per_sale": 0,
        "search_url": "https://www.webstaurantstore.com/search/{q}.html",
        "membership": "No membership needed.",
        "how_to_buy": ["Create an account. Look for case sizes and bulk pricing on the product page."]
        + COMMON_BUY_STEPS,
    },
    {
        "key": "walmart",
        "name": "Walmart Marketplace",
        "kind": "marketplace",
        "fee_pct": 15,
        "ship_per_sale": 4.0,
        "search_url": "https://www.walmart.com/search?q={q}",
        "membership": "Seller account required. Walmart reviews seller applications.",
        "how_to_buy": [
            "Apply for a Walmart Marketplace seller account and wait for approval.",
            "Create the listing. Match an existing item by UPC or add a new item.",
            "Set your price from the profit numbers here, after fees and shipping.",
            "Ship on time and track every order. Late shipping hurts seller ratings.",
            "Check category and brand rules before you list.",
        ],
    },
    {
        "key": "amazon",
        "name": "Amazon",
        "kind": "marketplace",
        "fee_pct": 15,
        "ship_per_sale": 4.0,
        "search_url": "https://www.amazon.com/s?k={q}",
        "membership": "Seller account required. Some categories and brands need approval.",
        "how_to_buy": [
            "Create a seller account. Some categories and brands need approval before you can list.",
            "Match the item by UPC or ASIN. Do not list items the brand restricts.",
            "Set your price from the profit numbers here, after fees and shipping.",
            "Decide who ships: you, or Amazon from its warehouse for an added fee.",
            "Keep the purchase invoices in case Amazon asks for proof of supply.",
        ],
    },
    {
        "key": "ebay",
        "name": "eBay",
        "kind": "marketplace",
        "fee_pct": 13.5,
        "ship_per_sale": 4.0,
        "search_url": "https://www.ebay.com/sch/i.html?_nkw={q}",
        "membership": "Seller account required.",
        "how_to_buy": [
            "Create a seller account.",
            "List the item with clear photos, the exact pack size, and an honest title.",
            "Set your price from the profit numbers here, after fees and shipping.",
            "Ship on time and keep tracking numbers.",
            "Check which brands and categories have listing rules.",
        ],
    },
]


def seed_sources(con):
    for s in SEED:
        con.execute(
            "INSERT OR IGNORE INTO sources.sources"
            "(key,name,kind,fee_pct,ship_per_sale,search_url,membership,how_to_buy,enabled) "
            "VALUES(?,?,?,?,?,?,?,?,1)",
            (
                s["key"],
                s["name"],
                s["kind"],
                s["fee_pct"],
                s["ship_per_sale"],
                s["search_url"],
                s["membership"],
                json.dumps(s["how_to_buy"]),
            ),
        )
