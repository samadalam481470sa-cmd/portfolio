# EstateIQ Data Model

EstateIQ uses three primary operational databases plus a derived score table.

## Property database

Table: `properties`

| Field | Description |
| --- | --- |
| `source_id` | Stable unique identifier from the source adapter |
| `address` | Street address |
| `city` | City |
| `county` | County |
| `state` | State abbreviation |
| `zip_code` | ZIP or postal code |
| `latitude` | Geocoded latitude |
| `longitude` | Geocoded longitude |
| `price` | Asking price or auction opening reference |
| `bedrooms` | Bedroom count |
| `bathrooms` | Bathroom count |
| `square_footage` | Interior square footage |
| `lot_size_sqft` | Lot size in square feet |
| `listing_status` | `active`, `pending`, `sold`, `off_market`, `foreclosure`, or `auction` |
| `listing_source` | Normalized source name |
| `date_listed` | Listing or discovery date |
| `property_type` | Residential, multifamily, townhome, commercial, etc. |
| `estimated_monthly_rent` | Rent estimate from feed, comps, or model |
| `metadata` | Source-specific JSON payload |

## Market database

Table: `market_snapshots`

| Field | Description |
| --- | --- |
| `market_id` | Stable period-specific market identifier |
| `city` | City |
| `county` | County |
| `state` | State abbreviation |
| `zip_code` | ZIP or postal code |
| `period` | Reporting period, for example `2026-Q2` |
| `median_price` | Median sale/list price |
| `median_price_per_sqft` | Median price per square foot |
| `average_rent` | Average monthly rent |
| `rent_growth_pct` | Rent growth percentage |
| `inventory_level` | Available inventory count |
| `days_on_market` | Median/average days on market |
| `sales_volume` | Closed sales volume |
| `appreciation_pct` | Appreciation trend |
| `population_growth_pct` | Population growth indicator |
| `job_growth_pct` | Job growth indicator |
| `building_permit_growth_pct` | Building permit growth |
| `new_business_growth_pct` | New business formation growth |
| `housing_demand_index` | Normalized 0-100 demand index |

## Contact database

Table: `contacts`

| Field | Description |
| --- | --- |
| `contact_id` | Stable unique identifier |
| `name` | Public business contact or organization name |
| `role` | Listing agent, broker, builder, auction contact, public records contact, etc. |
| `brokerage` | Brokerage or company, when applicable |
| `phone` | Public business phone |
| `email` | Public business email |
| `website` | Public website |
| `business_address` | Public business address |
| `city` | Contact market city |
| `state` | Contact market state |
| `source` | Source where the public contact was found |
| `property_source_id` | Optional property link |

## Investment score table

Table: `investment_scores`

Scores are derived data, not raw source data. Recalculate them when market snapshots, assumptions, or scoring weights change.

| Field | Description |
| --- | --- |
| `property_source_id` | Linked property identifier |
| `score` | Composite 0-100 investment score |
| `cap_rate_pct` | Estimated cap rate |
| `annual_cash_flow` | Estimated annual cash flow |
| `market_strength` | Normalized market momentum score |
| `value_score` | Relative price-per-square-foot value score |
| `demand_score` | Inventory and demand pressure score |
| `recommendation` | Priority grouping |
| `reasons` | JSON list of score explanations |
| `calculated_at` | Timestamp of score calculation |

## Source adapter rule

Each adapter should do three things:

1. Validate that required source fields exist.
2. Normalize into an EstateIQ domain model.
3. Preserve source-specific fields in `metadata` or source attribution fields.
