# DXB Interact

`dxbi_transactions` is the current source name, but the comprehensive scrape now
captures DXB Interact rental/property map data. It should be split after the
current raw backfill work:

- `dxbi_property_map` or `dxbi_rental_map` for map/building/unit payloads.
- `dxbi_transactions` reserved for true sales/rental transaction history.

Do not rename this source during an active run.

## Source Contract

- Provider: `dxbinteract`
- Dagster raw asset: `dxbi_transactions_raw`
- Checkpoint strategy: `date_window`
- Cadence: daily
- Bronze tables:
  - `dxbi_transactions_bronze` for legacy report-table rows.
  - `dxbi_heatmap_*_bronze` and `dxbi_fam_map_buildings_bronze` for the current
    comprehensive map payloads.

The source name is still historical. Comprehensive map rows now load into
source-specific heatmap bronze tables, while `dxbi_transactions_bronze` remains
limited to `report_tables`/`both` runs.

## Scrape Modes

- `comprehensive`: current default. Opens the rental map, queries map endpoints,
  dedupes buildings, fetches building/unit payloads, and full-replaces the
  heatmap bronze tables present in the raw manifest.
- `report_tables`: legacy APEX table scrape for visible sales/rental tables.
  Bronze replaces the affected date slices.
- `both`: runs comprehensive and report table modes in one release.

## Comprehensive Raw Files

- `dxbi_heatmap_rental_buildings.jsonl`: rental map discovery rows by query.
- `dxbi_heatmap_buildings.jsonl`: per-building detail payloads.
- `dxbi_heatmap_building_statuses.jsonl`: per-building status payloads.
- `dxbi_heatmap_chessboards.jsonl`: per-building floor/unit layout and rental
  status snapshot payloads.
- `dxbi_fam_map_buildings.jsonl`: FAM map building/project metadata.
- `dxbi_heatmap_errors.jsonl`: failed endpoint responses.

Each per-building file includes `location_id` and the original discovery `seed`
where applicable.

## R2 Layout

```text
raw/source=dxbi_transactions/extract_date=<date>/run_id=<run_id>/*.jsonl
raw/source=dxbi_transactions/manifests/<run_id>.json
```

## Config Notes

Important comprehensive knobs:

- `heatmap_property_types`: default `Apartment,Villa,Plot,Commercial`.
- `heatmap_bedrooms`: default `0` through `9`.
- `max_heatmap_buildings`: cap for smoke tests.
- `include_heatmap_building_details`
- `include_heatmap_building_status`
- `include_heatmap_chessboard`
- `include_fam_map_buildings`
- `heatmap_request_pause_seconds`: default conservative pause.
- `heatmap_fetch_timeout_seconds`: prevents one endpoint from blocking the run.
- `heatmap_progress_interval`: controls per-building progress logs.

## Operational Notes

The current comprehensive run writes local JSONL and uploads only after the
extractor returns. Future work should convert this to a chunked pattern:

1. Discovery run writes building IDs/seeds.
2. Payload hydration reads the discovery manifest and fetches building/status/
   chessboard/FAM payloads in resumable chunks.

That would make DXBI behave more like Reelly archive plus asset hydration.
