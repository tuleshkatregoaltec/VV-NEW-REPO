# Architecture

Holocron is being rebuilt around four concerns:

- `sources/`: one package per source connector
- `platform/`: shared R2-compatible object storage, ClickHouse, manifest,
  config, and runtime helpers
- `orchestration/`: Dagster definitions only
- `domain/`: cross-source and business-facing outputs

## Data Flow

The intended flow is:

```text
source connector
  -> immutable raw release in Cloudflare R2
  -> bronze ClickHouse table(s)
  -> optional domain outputs
```

Dagster sits beside the pipeline as the control plane for:

- asset catalog and lineage
- schedules and sensors
- checks and metadata
- retries and backfills

## Boundaries

The important ownership rules are:

- a source owns its extraction logic, raw release shape, and source-conformed bronze tables
- shared platform code must stay source-agnostic
- domain outputs may depend on many sources
- one source must not depend on another source's code
- Dagster must not contain source-specific scraping or parsing logic

## Current Core Types

The new package starts with a deliberately small contract surface:

- `SourceSpec`
- `RawFile`
- `RawRelease`
- `BronzeTable`

These are enough to define a source, shape immutable raw releases, and generate orchestration later without baking source internals into the control plane. Silver/domain layers are intentionally deferred until the raw and bronze source set is stable.
