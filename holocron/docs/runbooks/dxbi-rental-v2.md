# DXB Interact rental v2 runbook

The v2 pipeline treats DXB Interact as the coverage authority. DLD is a scoped
benchmark only. Raw data and checkpoints start at `2025-01-01`.

## Discover and validate coverage

Run discovery with the rental account. It reads authenticated filter choices and
the checked-in 213-area inventory, then writes a versioned manifest.

```bash
python scripts/dxbi_rental_backfill.py \
  --credentials /secure/account-b.json \
  --storage-state /secure/account-b-state.json \
  --browser /path/to/chrome \
  --output-dir /data/dxbi-rental-discovery \
  --start-date 2026-08-01 --end-date 2026-08-01 --direction desc \
  --account-id account-b \
  --manifest-path /secure/rental-profile-manifest.json \
  --discover-manifest
```

Validate at least one dense and one ordinary date. Validation scrapes the full
filter-profile × location matrix and updates `selected_configurations` to the
smallest deterministic union observed across those dates. A normal scrape refuses
to use a manifest whose validation status is not `complete`.

```bash
python scripts/dxbi_rental_backfill.py \
  --credentials /secure/account-b.json \
  --storage-state /secure/account-b-state.json \
  --browser /path/to/chrome \
  --output-dir /data/dxbi-rental-validation \
  --start-date 2026-07-01 --end-date 2026-07-02 --direction desc \
  --account-id account-b \
  --manifest-path /secure/rental-profile-manifest.json \
  --coverage-validation
```

## Backfill and load the shadow tables

Use a separate output directory so v1 checkpoints can never be reused. Request
budget exhaustion exits with code 2, writes `_FAILURE`, and does not create
`_SUCCESS`. Resume with the same command until every partition is complete.

```bash
python scripts/dxbi_rental_backfill.py \
  --credentials /secure/account-b.json \
  --storage-state /secure/account-b-state.json \
  --browser /path/to/chrome \
  --output-dir /data/dxbi-rentals-v2 \
  --start-date 2025-01-01 --end-date 2026-09-04 --direction desc \
  --account-id account-b \
  --manifest-path /secure/rental-profile-manifest.json

python scripts/load_dxbi_rental_events.py \
  --target shadow \
  --run-id rental-v2-backfill-20260904 \
  --reconciliation-output /data/dxbi-rentals-v2/load-reconciliation.json \
  /data/dxbi-rentals-v2
```

The loader re-normalizes retained JSONL files, writes quarantined records rather
than silently skipping them, enforces `raw_rows = normalized_rows +
quarantined_rows`, and rebuilds the v2 candidate projection.

## Validate, report, and cut over

Run one live daily cycle against the shadow tables and compare representative
dates to the manifest union. Publish the monthly DLD benchmark report:

```bash
python scripts/report_dxbi_rental_coverage.py \
  --end-date 2026-09-04 \
  --output /data/dxbi-rentals-v2/dld-coverage.json
```

The cutover command is validation-only unless `--activate` is supplied. It
requires a successful, zero-quarantine backfill reconciliation and v2 source-date
coverage through the cutover date. Each ClickHouse table exchange is atomic; if
the candidate exchange fails, the event exchange is rolled back. After exchange,
the old tables remain under the `_v2` names for rollback.

```bash
python scripts/activate_dxbi_rental_v2.py \
  --backfill-run-id rental-v2-backfill-20260904 \
  --cutover-date 2026-09-04

python scripts/activate_dxbi_rental_v2.py \
  --backfill-run-id rental-v2-backfill-20260904 \
  --cutover-date 2026-09-04 \
  --activate
```

The loader's default `--target auto` writes to shadow tables before cutover and
to canonical tables after the canonical event table exposes `contract_key`.

## Schedule and health

Install and enable the daily, weekly, and monthly rental timers. All three wait on
the same rental lock. The windows are D−14 through today, D−180 through D−15, and
D−365 through D−181 respectively. The sync/load job fails if no successful daily
run is present within 36 hours. ClickHouse exposes the same condition in
`dxbi_rental_ingestion_health`.
