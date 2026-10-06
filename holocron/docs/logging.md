# Logging

Holocron logs should make long runs understandable without attaching a debugger
or reading raw files mid-run.

## Standard Events

Use consistent event words in log messages:

- `starting`: run id, source, operation, relevant config summary.
- `authenticating` / `authenticated`: external user/session setup.
- `discovered`: rows, items, pages, IDs, or assets found.
- `selected`: subset planned for this run.
- `progress`: completed/total, errors, skipped, bytes, elapsed.
- `checkpoint`: next cursor, range, page, or shard.
- `completed`: final counts, bytes, manifest key or inventory key.
- `failed`: item identifier, endpoint/target key, status, error.

## Required Counts

For long-running jobs, progress logs should include the counts needed to answer:

- How much work was discovered?
- How much was selected for this run?
- How far through the selected work are we?
- How many records/assets succeeded?
- How many were skipped?
- How many failed?
- How many bytes were downloaded or uploaded?

## Identifiers

Failure logs should include stable identifiers:

- Source name and run id when available.
- Page/date/query/window for discovery failures.
- Project/listing/building/location id for item failures.
- Target R2 key for asset failures.
- Endpoint or source URL when relevant.

## Progress Cadence

Use a cadence that gives useful overnight feedback:

- Small jobs: start and completed logs are enough.
- Medium jobs: every 25-100 items or every few pages.
- Large asset hydration: every N completed futures plus byte totals.
- Slow per-item jobs: log every 1-5 minutes or every small batch.

Sparse logs can look like a hang. If one item can take more than a minute, add
endpoint-level timeouts and log errors instead of blocking indefinitely.

## Example Messages

```text
source: starting raw extraction run_id=<run_id> cursor=<cursor> pages_per_run=5
source: fetched list page=12 items=50 accumulated=600
source: fetching item payloads count=3258 discovered=3258
source: progress items=400/3258 errors=0 bytes=123456789
source: completed raw extraction run_id=<run_id> files=5 rows=10000 bytes=...
source: checkpoint next_page=17 completed=false manifest_key=...
```

## What Not To Log

- Secrets, credentials, auth tokens, full cookies, or signed headers.
- Huge raw payloads.
- Repeated identical per-row logs when aggregate progress is enough.
- Ambiguous success messages without counts.
