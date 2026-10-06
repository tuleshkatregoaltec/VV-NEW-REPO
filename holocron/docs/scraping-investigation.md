# Scraping Investigation

This playbook captures how to investigate new or fragile data sources before
turning them into durable Holocron scrapes.

## Start With Classification

Classify what the provider endpoint really returns:

- Listing snapshot.
- Transaction history.
- Building/project metadata.
- Map aggregate.
- Unit layout/status.
- Media/document asset.
- Lookup/filter taxonomy.

Use the source name and raw file names to match this classification. Avoid
calling map aggregates or snapshots "transactions" unless they are true
transaction records.

## Inspect Network Behavior

When a site-backed source is involved:

- Open the page in Playwright or a browser.
- Capture fetch/XHR endpoints, request bodies, headers, and response shapes.
- Identify pagination, filters, caps, and sort order.
- Test whether endpoints work from direct HTTP or only browser context.
- Record any required signatures, cookies, anti-bot behavior, or storage state.

Keep source-specific protocol logic inside `holocron/sources/<source>/extract.py`.

## Probe Data Depth

For each endpoint, establish:

- Row grain.
- Stable IDs.
- Available time range.
- Query parameters that change result depth.
- Maximum page/result caps.
- Whether rows are current snapshots or historical records.
- How to dedupe across overlapping queries.

## Build The Smallest Smoke

Before a backfill, run a bounded smoke:

- One query, one page, one date window, or one item.
- One or a few detail payloads.
- Logging visible in Dagster or a local log file.
- Raw files inspected for row counts and key fields.

Do not start a full backfill until the smoke proves the endpoint, file writing,
and upload path.

## Decide The Ingestion Pattern

Use `docs/ingestion-patterns.md`:

- Chunked raw scrape for structured rows.
- Asset hydration for media/documents.
- Avoid long local-only runs except during first investigation.

## Anti-Bot And Captcha

Prefer the least fragile path:

- Direct HTTP if stable.
- Browser-context fetch if the site computes headers/signatures.
- Headful Chromium/Xvfb when headless is blocked.
- Storage state only when a reusable browser-cleared session is necessary.
- Captcha solving only when the source cannot be accessed otherwise.

Record the chosen approach in the source README.

## Preserve Raw Context

Raw rows should preserve enough context to remodel later:

- Original query/body/filter.
- Source page or endpoint.
- Provider IDs.
- Parent IDs or seed rows.
- Full raw payload where feasible.

This lets us defer bronze modeling without losing relationships.
