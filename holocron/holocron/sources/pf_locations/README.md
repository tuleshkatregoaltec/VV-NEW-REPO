# Property Finder Locations

`pf_locations` extracts Property Finder Dubai location hierarchy and filter
settings. It is planning data for Property Finder listing scrapes.

## Source Contract

- Provider: `propertyfinder`
- Dagster raw asset: `pf_locations_raw`
- Dagster bronze asset: `pf_locations_bronze`
- Checkpoint strategy: `full_refresh`
- Cadence: manual

## Raw Files

- `pf_locations_pages.jsonl`: raw paginated location responses.
- `pf_locations.jsonl`: normalized discovered location rows with raw context.
- `pf_filter_settings.jsonl`: listing filter/settings payloads.

## R2 Layout

```text
raw/source=pf_locations/extract_date=<date>/run_id=<run_id>/*.jsonl
raw/source=pf_locations/manifests/<run_id>.json
```

## Config Notes

Important knobs:

- `categories`: Property Finder category IDs.
- `location_page_limit`: page size for location requests.
- `max_location_pages`: cap for discovery.
- `only_dubai`: restricts output to Dubai context.
- `dubai_location_id`: default root location id.

## Operational Notes

Run this before broad `pf_listings` snapshots when location/filter assumptions
need refreshing. The manual full-fetch job now updates bronze by atomically
replacing the current location table from the complete raw hierarchy.
