# DLD Open Data

The `dld_od_*` sources archive Dubai Land Department open-data endpoint rows as
raw JSONL. They share `holocron/sources/dld_open_data_shared.py`; each source
package only declares the endpoint command, default filters, sort, file names,
and source contract.

## Sources

- `dld_od_transactions`
- `dld_od_rents`
- `dld_od_projects`
- `dld_od_valuations`
- `dld_od_buildings`
- `dld_od_developers`
- `dld_od_lands`
- `dld_od_units`
- `dld_od_brokers`

## Raw Files

Each endpoint writes two files:

```text
dld_od_<category>_rows.jsonl
dld_od_<category>_pages.jsonl
```

Rows contain the provider row payload plus scrape metadata. Page rows contain
request payloads, pagination metadata, and response-level diagnostics.

## R2 Layout

```text
raw/source=dld_od_<category>/extract_date=<date>/run_id=<run_id>/*.jsonl
raw/source=dld_od_<category>/manifests/<run_id>.json
state/source=dld_od_<category>/operation=backfill_chunk.json
state/source=dld_od_<category>/operation=snapshot_chunk.json
```

## Runtime Modes

- `incremental`: default scheduled mode. Uses a lookback window ending at the
  run date, writes raw, then updates the affected bronze date windows.
- `backfill`: manual dated window. Requires `start_date` and `end_date`.
- `snapshot`: manual full endpoint scan. Date-capable inventory endpoints that
  cannot sensibly snapshot through date windows omit date filters when their
  endpoint contract sets `snapshot_omits_date_filters=true`.

## Dagster Jobs

Each source has the same job shape:

- `dld_od_<category>_daily_incremental`: scheduled raw + bronze incremental job.
- `dld_od_<category>_manual_backfill`: unscheduled raw-only dated backfill.
- `dld_od_<category>_manual_snapshot`: unscheduled raw-only snapshot.

The daily schedules are staggered between 04:00 and 05:30 UTC. Unit data is
scheduled like the other endpoints even if the provider endpoint is unreliable,
so the job is ready when the upstream behavior improves.

Incremental runs do not currently resume `max_pages` cursors across scheduled
runs. Treat `max_pages` on daily incremental jobs as a per-run cap for bounded
polling, not as durable resumability. Manual snapshot and backfill jobs keep
checkpointed cursors because their windows are operator-controlled.

Bronze loaders reject incomplete DLD raw chunks for current-state loads. Keep
manual chunked backfills raw-only until the selected raw manifests represent
complete windows, then replay them into bronze in order.

## Config Notes

Important knobs:

- `mode`: `incremental`, `backfill`, or `snapshot`.
- `start_date`, `end_date`: required for backfill.
- `lookback_days`: incremental window size.
- `slice_days`: days per request window.
- `page_size`, `max_pages`: pagination controls.
- `window_cursor`, `skip_cursor`: resume cursors written to checkpoint metadata.
- `sort`, `filters`: optional endpoint overrides.
