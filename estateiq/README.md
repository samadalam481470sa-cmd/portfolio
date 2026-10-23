# EstateIQ

EstateIQ is a real estate intelligence platform foundation that collects listings, market indicators, migration and growth signals, and publicly available contact records, then scores properties for investment focus.

This repository contains a runnable first implementation of the product described in the guide:

- Normalized property, market, and public contact databases
- Pluggable source adapters for listing, market, and contact feeds
- Investment scoring for cap rate, cash flow, market strength, demand, and value
- Ranked opportunities with reasons and recommendations
- AI-style investment report generation from structured data
- JSON API and a browser website with ranked deals, map pins, and report modals
- Seed data covering MLS, county foreclosure, builder inventory, and auction sources

## Requirements

- Python 3.11 or newer
- No runtime third-party dependencies

## Quick start

### Open from a phone or any browser after deployment

This project includes a GitLab Pages configuration for the static website. After the branch is merged and the Pages pipeline finishes, the site should be available at:

```text
https://samad.alam481470sa-group.gitlab.io/samad.alam481470sa-project/
```

Use this public Pages URL on iPhone/Safari. Do not use `localhost` on your phone unless the server is running on that same phone.

### Open immediately without a server

You can open the static demo website directly:

```text
web/index.html
```

Double-click that file, or open it in your browser. This mode uses embedded demo data and does not need Python running.

### Run the live local server

For Safari or another browser on your own computer, the easiest command is:

```bash
python3 open_website.py
```

This starts the site, prints the exact local URL, and opens your default browser. Keep that terminal open while using the website.

If you are using Replit or another editor with a Run button, run `main.py`.

If you are using a terminal, run:

```bash
PYTHONPATH=src python3 -m estateiq.seed
PYTHONPATH=src python3 -m estateiq.api --seed
```

Do not paste the terminal command into a `.py` file. Python files need Python code; terminal commands need to be run in the shell.

Server mode is required for live database-backed API routes, refreshed scoring, and generated reports from the Python backend.

Open:

- Website: <http://127.0.0.1:8080/>
- Health check: <http://127.0.0.1:8080/health>
- Properties: <http://127.0.0.1:8080/properties>
- Ranked opportunities: <http://127.0.0.1:8080/opportunities>
- GeoJSON map data: <http://127.0.0.1:8080/map-data>
- Opportunity map alias: <http://127.0.0.1:8080/map>
- Example report: <http://127.0.0.1:8080/properties/mls-atl-1001/report>

### Safari localhost troubleshooting

- `localhost` only works on the same computer where the Python server is running.
- On an iPhone, `localhost` means the iPhone itself.
- If you are using Replit, Cursor Cloud, GitLab, or another remote workspace, Safari on your laptop cannot use that remote machine's `localhost`; use the platform's web preview URL instead.
- If `8080` is already busy, `open_website.py` will choose another port and print the correct URL.
- If you do not need backend features, open `web/index.html` directly in Safari.

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Core data stores

EstateIQ initializes four SQLite tables:

1. `properties` - address, geography, price, listing details, source, and source metadata.
2. `market_snapshots` - historical price, rent, inventory, sales, appreciation, migration, jobs, permits, and business growth indicators.
3. `contacts` - publicly available listing agent, broker, builder, auction, county, and property manager contacts.
4. `investment_scores` - derived opportunity rankings and score explanations.

The first three tables map to the platform's primary databases. Scores are generated from those stores and can be recalculated whenever new data arrives.

## Data collection

The initial adapters load JSON feeds from `data/`:

- `properties.json`
- `markets.json`
- `contacts.json`

New feeds should implement the `DataSource` protocol in `estateiq.data_sources` and normalize records into the domain models. This keeps licensed MLS feeds, county records, public property records, auction sites, broker sites, and builder inventory behind one collection contract.

## Investment scoring

The scoring engine evaluates:

- Estimated cap rate
- Estimated annual cash flow
- Price per square foot versus market median
- Population, job, rent, appreciation, permit, and business growth
- Inventory, days on market, and demand pressure

Recommendations are grouped as:

- `Priority target`
- `Strong watchlist`
- `Needs underwriting`
- `Monitor only`

## Documentation

- Product blueprint: `docs/product_blueprint.md`
- Data model: `docs/data_model.md`

## Compliance note

Use licensed data where required and respect each source's terms of service. Contact records should be limited to publicly available business contact information, not private personal data.
