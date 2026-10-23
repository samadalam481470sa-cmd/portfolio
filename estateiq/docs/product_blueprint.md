# EstateIQ Product Blueprint

EstateIQ is designed as a data aggregation, analytics, and intelligence platform for real estate investors. It is not a listing clone; listings are only one input into a wider opportunity engine.

## Five product questions

### 1. What properties are available?

The platform normalizes active and distressed inventory from:

- Licensed MLS feeds
- Broker websites
- Auction platforms
- Foreclosure databases
- Builder and new construction inventory
- County and public property records

All source adapters should map source-specific payloads into the `Property` model while preserving raw source-specific fields in `metadata`.

### 2. Where are people moving?

Market snapshots track growth and demand indicators by ZIP/city:

- Population growth
- Job growth
- Rent growth
- Housing demand
- Building permit growth
- New business growth
- Inventory and days on market
- Appreciation trends

These indicators feed the market strength and demand components of the investment score.

### 3. Which deals are the best?

The scoring engine ranks opportunities using:

- Estimated cap rate
- Estimated annual cash flow
- Price per square foot discount or premium
- Appreciation and rent growth
- Population, job, permit, and business momentum
- Inventory pressure and days-on-market speed

Scores are stored separately from source records so the model can be recalculated as assumptions and data improve.

### 4. Who can be contacted?

The contact database stores public business contact information only:

- Listing agents
- Brokerages
- Property managers
- Builders and developers
- Auction contacts
- Public agency contacts

Private personal contact data should not be stored.

### 5. What should investors focus on?

The platform ranks opportunities and generates structured investment reports with:

- Executive summary
- Positives
- Risks
- Public contact next step
- Underwriting next steps

## Current implementation

The first implementation is intentionally lightweight and dependency-free:

- SQLite persistence
- JSON seed adapters
- Standard-library HTTP API
- Local map page consuming GeoJSON
- Unit tests for the core collection, scoring, and report flow

## Expansion roadmap

### Data acquisition

- Add licensed MLS feed adapter.
- Add county record scraper/API adapters where permitted.
- Add foreclosure and auction source adapters.
- Add new construction and builder inventory adapters.
- Add scheduled refresh jobs with source-level observability.

### Analytics

- Add historical market trend tables.
- Store underwriting assumptions per investor profile.
- Add comparable rental and sale selection.
- Add deal alerts when scores cross thresholds.
- Add model versioning for score reproducibility.

### Product experience

- Replace local HTML map with a full web frontend.
- Add saved searches and tracked markets.
- Add report export.
- Add contact verification and source attribution.
- Add role-based access and audit logs.

### Compliance and data governance

- Track data source licensing and terms.
- Retain source URLs and collection timestamps.
- Store only public business contact records.
- Add deletion and correction workflows for contact data.
