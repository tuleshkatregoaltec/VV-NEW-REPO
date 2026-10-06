# Reelly Supply

`reelly_supply` archives Reelly project supply data and supports follow-on
hydration for project documents and media.

## Source Contract

- Provider: `reelly`
- Dagster raw asset: `reelly_supply_raw`
- Dagster bronze asset: `reelly_supply_bronze`
- Operational job: `reelly_supply_archive_chunk`
- Checkpoint strategy: `cursor_pages`
- Cadence: daily/manual chunks

## Archive Raw Files

- `reelly_supply_project_list_pages.jsonl`: project search/list pages.
- `reelly_supply_project_details.jsonl`: project detail payloads.
- `reelly_supply_project_documents.jsonl`: discovered document/media/link rows
  with source field paths.
- `reelly_supply_matrix_availability.jsonl`: availability probe rows.
- `documents/project_id=<id>/...`: optional raw document downloads when enabled.

## R2 Layout

```text
raw/source=reelly_supply/extract_date=<date>/run_id=<run_id>/*
raw/source=reelly_supply/manifests/<run_id>.json
state/source=reelly_supply/operation=archive_chunk.json
```

The archive checkpoint records the next page and last manifest key after a
successful upload.

## Asset Hydration

Reelly document/media hydration jobs read previous raw manifests from R2 and
write stable media keys plus inventory manifests.

Jobs/assets:

- `reelly_supply_document_assets_backfill`
- `reelly_supply_project_media_assets_backfill`

Hydration behavior:

- Plan assets from `reelly_supply_project_documents.jsonl` and project details.
- Preserve project id, source row, field path, asset type, and source URL.
- Skip existing target keys unless overwrite is enabled.
- Upload each downloaded file directly to R2.
- Write inventory JSONL with status, bytes, hash, content type, target key, and
  errors.

## Config Notes

Archive knobs:

- `pages_per_run`: default chunk size.
- `page_cursor`: usually resolved from checkpoint.
- `download_documents`: default `false`; raw extraction discovers document URLs
  and leaves file transfer to the document/media hydrators unless this is
  explicitly enabled.
- `download_all_project_docs`
- `try_matrix_availability`
- `allowed_document_hosts`
- `max_document_mb`

Hydration knobs:

- `manifest_prefix`
- `manifest_keys`
- `latest_manifest_count`
- `target_prefix`
- `inventory_prefix`
- `max_assets_per_run`
- `max_concurrent_downloads`
- `overwrite_existing`
- `asset_type_allowlist`

## Operational Notes

The archive scrape is chunked and checkpointed. The scheduled catalog and
availability deltas update current-state bronze for touched project,
document, and availability keys. The hydration jobs are
idempotent and upload per asset, so they are better suited for long media
backfills than source scrapes that only upload at the end. The scheduled catalog
delta runs raw extraction together with document and project-media hydration,
limiting hydration to the latest raw manifest, then selecting missing assets
before applying the per-run limit.
