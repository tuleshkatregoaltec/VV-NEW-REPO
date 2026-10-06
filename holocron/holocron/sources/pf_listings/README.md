# Property Finder Listings

`pf_listings` captures Property Finder Dubai sale and rental listing snapshots
with adaptive query partitioning, chunked search-page collection, chunked
listing detail fetches, and media hydration. Search pages are collected through
the public `/en/search` HTML route and their embedded Next.js payload.

## Source Contract

- Provider: `propertyfinder`
- Dagster raw asset: `pf_listings_raw`
- Checkpoint strategy: `partitioned_chunks`
- Cadence: manual
- Operational jobs:
  - `pf_listings_plan_snapshot`
  - `pf_listings_search_chunk`
  - `pf_listings_detail_chunk`
  - `pf_listings_daily_latest_delta`
- Media hydration asset: `pf_listing_media_assets`
- Bronze asset: `pf_listings_bronze`

## Raw Files

- `pf_listing_filter_settings.jsonl`
- `pf_listing_location_partitions.jsonl`
- `pf_listing_query_plan.jsonl`
- `pf_listing_plan_state.jsonl`
- `pf_listing_search_pages.jsonl`
- `pf_listing_properties.jsonl`
- `pf_listing_details.jsonl`

The search/detail rows preserve listing IDs, query context, pagination context,
and raw provider payloads.

## Media Hydration

Property Finder listing media should be handled through the media asset hydrator:

- Read `pf_listing_properties.jsonl` and `pf_listing_details.jsonl` from raw
  manifests.
- Plan deterministic media keys.
- Skip existing objects.
- Upload each asset to R2.
- Write an inventory manifest with status counts.

## R2 Layout

```text
raw/source=pf_listings/extract_date=<date>/run_id=<run_id>/*.jsonl
raw/source=pf_listings/manifests/<run_id>.json
state/source=pf_listings/operation=plan_snapshot.json
state/source=pf_listings/operation=search_chunk.json
state/source=pf_listings/operation=detail_chunk.json
raw/source=pf_listings/listing_media_asset_manifests/run_id=<run_id>/pf_listing_media_assets.jsonl
```

## Config Notes

Important knobs:

- `categories`: Property Finder category IDs.
- `location_ids`: default Dubai root.
- `max_pages_per_query`: Property Finder caps at 50.
- `max_results_per_query`: planning threshold for partitioning.
- `max_planned_queries`
- `max_plan_queries_per_run`: planning work saved per durable plan chunk.
- `max_search_pages_per_run`
- `max_partition_depth`
- `split_by_property_type`, `split_by_location`, `split_by_bedrooms`,
  `split_by_price`
- `fetch_details`
- `max_details_per_run`
- `mode`: `snapshot`, `plan`, `search`, or `details`.
- `manifest_keys`: optional exact raw manifest keys for media hydration.
- `latest_manifest_count`: optional latest-manifest limit for media hydration;
  the scheduled latest-delta job defaults this to `1`.
- `plan_manifest_s3_key`: search chunks normally resolve this from the plan
  checkpoint.
- `search_query_cursor`, `search_page_cursor`: normally resolved from the
  search checkpoint.
- `detail_manifest_cursor`, `detail_row_cursor`: normally resolved from the
  detail checkpoint.
- `block_media_requests`: keeps the browser scrape focused on data, not images.

## Operational Notes

The durable path is chunked:

1. Run `pf_listings_plan_snapshot` repeatedly. Each run publishes a query-plan
   fragment plus `pf_listing_plan_state.jsonl`, then advances
   `plan_snapshot`. When the checkpoint says `completed=true`, the accumulated
   plan manifests are ready for search.
2. Run `pf_listings_search_chunk` repeatedly. It reads the plan checkpoint,
   fetches up to the configured page budget, writes search/property rows, and
   advances `search_chunk` only after the raw manifest exists. The default page
   budget is deliberately chunked so slow provider responses cannot waste hours
   of in-memory progress.
3. Run `pf_listings_detail_chunk` repeatedly. It reads property rows from prior
   raw manifests, fetches listing detail `__NEXT_DATA__`, and advances
   `detail_chunk` only after the raw manifest exists.
4. Run `pf_listing_media_assets_backfill` to hydrate associated images/media.
   The scheduled latest-delta job also updates bronze for observed listing and
   detail keys, then runs this hydration so new listing media lands in R2 with
   the raw ingest.

`pf_listings_manual_snapshot` remains available for bounded smoke tests, but it
is intentionally not the preferred path for broad backfills because a single
long process uploads only at the end. A full Dubai sale-and-rental backfill
uses the plan, search, and detail jobs in that order; the query planner splits
result sets that exceed Property Finder's 50-page window before collection.

Current-state bronze is only as complete as the observed Property Finder rows.
Latest-delta runs upsert seen listing keys and refreshed detail keys; they do
not infer tombstones for listings that disappear outside the scanned pages.
