# Ingestion Patterns

Holocron sources should make raw data durable before doing any modeling work.
This doc covers raw ingestion only. Bronze loading patterns are in
`docs/bronze-patterns.md`.

## Durable Commit Point

The durable commit point is:

1. Raw data files uploaded to object storage.
2. A raw manifest written under `raw/source=<source>/manifests/<run_id>.json`.
3. Any source checkpoint advanced only after the manifest exists.

Local scratch files are an implementation detail. A long-running source should
not depend on hours of local scratch state as its only copy of progress.

## R2 Layout

Raw release files use the shared manifest helpers:

```text
raw/source=<source>/extract_date=<YYYY-MM-DD>/run_id=<run_id>/<file>
raw/source=<source>/manifests/<run_id>.json
state/source=<source>/operation=<operation>.json
```

Media and document assets use app-facing stable keys, usually under `media/`,
and write separate inventory manifests under the raw source hierarchy.

## Chunked Raw Scrape

Use this for API, table, map, and page scrapes that produce structured raw
files.

The source should:

- Bound each run by page range, date range, ID shard, or query shard.
- Write local JSONL/CSV files for only that chunk.
- Return a `RawRelease`.
- Let the generic raw asset wrapper upload files and the manifest.
- Advance the checkpoint only after upload succeeds.

This is the preferred pattern for Reelly archive chunks, DLD daily slices,
DDA full refreshes, and DXBI map chunks.

## Asset Hydration

Use this for media, documents, or large binary payloads discovered from previous
raw manifests.

The hydrator should:

- Read source manifests from R2.
- Plan deterministic target keys.
- Check `object_exists` before downloading unless overwrite is explicit.
- Download and immediately upload each asset to R2.
- Write an inventory JSONL with source row, target key, status, bytes, hash,
  content type, and error.

This is the preferred pattern for Reelly project media/documents and Property
Finder listing media.

## Long Local Scrape

Avoid this except for short smoke tests or first investigations. A single run
that scrapes for hours and uploads only at the end is fragile because a process
failure loses local progress.

When this pattern appears in a new source, convert it to chunked raw scrape or
asset hydration before relying on it for repeated backfills.

## Source Naming

`SourceSpec.name` should name the durable dataset, not the provider. Prefer names
that match the actual raw data grain:

- `dxbi_property_map`, not `dxbi_transactions`, for building/unit map payloads.
- `dxbi_transactions` only for true sales or rental transaction history.
- `pf_listings` for listing search/detail snapshots.
- `pf_locations` for location/filter discovery.

If a source changes meaning during investigation, let the current run finish,
then rename/split the source in a follow-up migration.

## Raw File Guidance

- Prefer JSONL for record-oriented API/page output.
- Prefer CSV only when the source is naturally tabular and the schema is stable.
- Preserve full provider payloads in a `raw` or `payload` field when feasible.
- Include request/query context on every row.
- Include `_run_id`, `_scraped_at`, and source identifiers where the extractor
  can provide them.
- Keep binary assets out of raw JSONL; store them as media keys with inventory
  manifests.

## Smoke Tests

Every new or changed scraper should have a tiny live smoke path:

- One page, one query, one date, or one item.
- Bounded output.
- Clear log lines.
- No bronze dependency unless the task is explicitly bronze work.
- A quick sanity check that row counts and raw file names match expectations.
