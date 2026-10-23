# Wholesale Hub

Wholesale Hub finds products that sell for more on a marketplace than they cost at a wholesale store. It shows live price moves, the best deals, trending products, the most popular and most searched products, and the cheapest place to buy each one. Every deal comes with links and buying steps.

The hub starts with SAMPLE data so you can try every screen. Real prices come from CSV files, from eBay's API, or from connectors you add. Read "What is real and what is sample" before you trust any number.

## Start it

On a Mac, double-click `start.command`. The first run sets itself up, then opens the dashboard at http://127.0.0.1:8800.

In Terminal instead:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

You need Python 3.9 or newer.

## The screens

1. Best deals. Buy at one store, sell at another. Profit per sale, margin, and return on cost. Filter, sort, and export to CSV.
2. Trending now. Products whose searches are rising fastest.
3. Most popular. Searches over 24 hours plus marketplace sales rank.
4. Most searched. Raw search counts.
5. Cheapest to buy. The lowest unit price for each product and how far below the average it is.
6. Live feed. Every price move and every new deal as it happens.
7. Sources and fees. Edit each store's fee and shipping estimate. Profit updates at once.
8. Import data. Upload a CSV of real prices.

Click any product to see every store's offer, the price history, the profit for each pair, a profit calculator, and step-by-step buying and selling notes for the best pair.

## What is real and what is sample

1. The demo provider makes up products, brands, prices, searches, and sales ranks. Everything it makes is marked SAMPLE, and a yellow banner shows while any sample data exists.
2. Links on sample rows are store search links, not product links.
3. Turn the demo off when you load real data. In `config.json`: `{"providers": {"demo": {"enabled": false}}}`. Delete the `data` folder to remove the sample rows.
4. Fee percentages and shipping per sale are estimates. Replace them with your real numbers.

## Load real prices

Option 1: CSV. Use the Import data tab, or drop files in the `imports` folder. Each row is one product at one store. Rows with the same `upc` or `product_key` are matched as the same product. The template is at `/api/import/template.csv`. You can export price sheets from supplier portals, price-tracking tools you pay for, or your own research.

Option 2: eBay. `hub/providers/ebay.py` reads eBay's Browse API with your own developer keys. It is off by default and has not been tested against the live API. Add keys in `config.json` and turn it on.

Option 3: your own connector. Copy `hub/providers/template.py`, fill in `poll()`, and register it in `hub/providers/__init__.py`. Good sources are official store or marketplace APIs, affiliate and partner feeds, and paid data vendors.

## The five databases

Each one is its own SQLite file in the `data` folder.

| File | What it holds |
| --- | --- |
| `catalog.db` | Products: name, brand, category, UPC. |
| `prices.db` | Current offers per store, every price change, and daily summaries. |
| `trends.db` | Searches per minute, sales ranks, and the trend and popularity scores. |
| `opps.db` | Every profitable buy-here, sell-there pair, plus deal alerts. |
| `sources.db` | Stores, fees, buying steps, provider health, import log. |

Reads never wait on writes. One writer works at a time.

## How live updates and the daily refresh work

1. Each provider is polled every `tick_seconds` (1 second by default). New prices are saved, profit is recalculated for the products that changed, and the dashboard gets the change through a live stream.
2. Scores are recalculated every 10 seconds.
3. Once a day, at `daily_refresh_hour` (3 AM by default), the hub asks each provider for a full refresh, rolls old price changes into daily summaries, deletes expired rows, and recalculates every deal. You can run it any time from the Sources and fees tab.
4. Per-second updates are real only when the source can deliver them. The demo can. Real stores and APIs have rate limits, so real providers poll more slowly. Set each provider's interval to what its terms allow.

## How the numbers are calculated

```
cost    = buy unit price x units in the marketplace pack
fees    = marketplace price x marketplace fee %
profit  = marketplace price - fees - shipping per sale - cost
margin  = profit / marketplace price
roi     = profit / cost
trend   = (searches per minute, last 15 min - per minute, 45 min before)
          / (per minute, 45 min before + 1)
popular = 70% searches in 24 h (against the busiest product) + 30% best sales rank
```

Only pairs with profit above zero are stored. A deal alert fires when profit and margin both pass `alert_min_profit` and `alert_min_margin_pct`.

The profit math does not include taxes, returns, storage, ad costs, or your time.

## Settings

Copy `config.example.json` to `config.json` and change only what you need. All settings and their defaults are in `hub/config.py`.

## Size and speed

These numbers were measured on a Linux test machine with the demo provider. Your Mac will differ.

| Products | Offers | Time to load | Memory | List screens | Cheapest screen |
| --- | --- | --- | --- | --- | --- |
| 5,000 | 20,030 | about 2 s | 90 MB | under 10 ms | 0.05 s |
| 20,000 | 79,873 | about 5 s | 133 MB | under 10 ms | 0.24 s |

Millions of products need a stronger database. The code keeps all database access in `hub/db.py` and `hub/engine.py`, so a move to PostgreSQL is contained. The Cheapest screen would also need caching at that size.

## Keep it running all day on a Mac

1. `start.command` already asks macOS not to sleep while the hub runs. System sleep is blocked only on power, so keep the charger in.
2. To run it as a double-click app with a menu and live editing, use the Mac app builder file. Set `START_COMMAND` to `./.venv/bin/python run.py` and `PORT` to `8800`.
3. To restart it after a crash or reboot, run it under launchd with KeepAlive.

## Limits and rules

1. No tool can honestly list every product on every store site with per-second prices. Stores do not publish open feeds of every product. Live data needs official APIs, partner programs, or paid data vendors.
2. Scraping store sites every second breaks their terms and gets blocked. This project does not scrape.
3. Link formats and fee rules change. Search links for each store are editable in the sources table.
4. Many brands restrict resale, and some marketplace categories need approval. Check each one before you buy stock.
5. Prices and stock change quickly. Confirm on the store page before you buy.

## Test it

```
python3 tests/smoke_test.py
```

This starts a private copy of the hub and checks 17 things, including the profit math, CSV import, fee changes, and the live stream.
