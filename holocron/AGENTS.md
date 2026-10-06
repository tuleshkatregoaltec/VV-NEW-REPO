# AGENTS.md

These rules apply to every task in this project unless explicitly overridden.
Bias: caution over speed on non-trivial work. Use judgment on trivial tasks.

## Rule 1 — Think Before Coding
State assumptions explicitly. If uncertain, ask rather than guess.
Present multiple interpretations when ambiguity exists.
Push back when a simpler approach exists.
Stop when confused. Name what's unclear.

## Rule 2 — Simplicity First
Minimum code that solves the problem. Nothing speculative.
No features beyond what was asked. No abstractions for single-use code.
Test: would a senior engineer say this is overcomplicated? If yes, simplify.

## Rule 3 — Surgical Changes
Touch only what you must. Clean up only your own mess.
Don't "improve" adjacent code, comments, or formatting.
Don't refactor what isn't broken. Match existing style.

## Rule 4 — Goal-Driven Execution
Define success criteria. Loop until verified.
Don't follow steps. Define success and iterate.
Strong success criteria let you loop independently.

## Rule 5 — Surface conflicts, don't average them
If two patterns contradict, pick one (more recent / more tested).
Explain why. Flag the other for cleanup.
Don't blend conflicting patterns.

## Rule 6 — Read before you write
Before adding code, read exports, immediate callers, shared utilities.
"Looks orthogonal" is dangerous. If unsure why code is structured a way, ask.

## Rule 7 — Tests verify intent, not just behavior
Tests must encode WHY behavior matters, not just WHAT it does.
A test that can't fail when business logic changes is wrong.

## Rule 8 — Checkpoint after every significant step
Summarize what was done, what's verified, what's left.
Don't continue from a state you can't describe back.
If you lose track, stop and restate.

## Rule 9 — Match the codebase's conventions, even if you disagree
Conformance > taste inside the codebase.
If you genuinely think a convention is harmful, surface it. Don't fork silently.

## Rule 10 — Fail loud
"Completed" is wrong if anything was skipped silently.
"Tests pass" is wrong if any were skipped.
Default to surfacing uncertainty, not hiding it.

# Repository Guidelines

## Project Shape
This repo is the `holocron` Python/Dagster runtime package.

- New runtime work should go into `holocron/`.
- Source packages live under `holocron/sources/<source>/`.
- Shared platform/runtime helpers live under `holocron/platform`.
- Dagster orchestration helpers live under `holocron/orchestration`.
- ClickHouse schema SQL lives in `holocron/lib/sql/clickhouse_schema.sql`.
- Tests live under `tests`.
- Handwritten downstream assets that derive new tables from already-published source tables belong in `holocron/assets/`.

## Stack And Tooling
- Runtime stack: Python 3.11, Dagster, ClickHouse, PostgreSQL, S3/R2-style object storage, and Pydantic settings.
- `just` is the canonical command interface. Use `just --list` before inventing ad-hoc commands.
- `uv` is the package manager and virtualenv runner.
- Ruff handles linting and formatting. Line length is 100, target is Python 3.11.
- `ty` handles type checking.
- `pytest` handles tests.

Common commands:

- Install deps: `just sync`
- Format: `just fmt`
- Run all tests: `just test`
- Typecheck: `just typecheck`
- Run the full verification pass: `just check`
- Prepare local env file: `just env local`
- Start the local stack: `just up local`
- Stop the local stack: `just down local`

For VPS-oriented replication and deploy work, prefer repo recipes such as `just env prod`, `just up prod`, and `just deploy`.

## Core Workflow
- Prefer `just` recipes for setup, linting, formatting, tests, type checks, local stack work, replication, and deploys.
- Use `.env.local` for local development configuration and do not commit secrets or local-only data.
- Prefer the narrowest useful check first, then broader checks when the change warrants it.
- In handoffs, mention the meaningful checks run and any checks intentionally skipped.

## Source Development
Each source should normally live under `holocron/sources/<source>/`:

- `source.py` contains the declarative source contract.
- `extract.py` contains source-local extraction logic.
- Optional source-local modules such as `bronze.py`, `parse.py`, `assets.py`, or `orchestration.py` should stay inside that source package when the behavior is source-specific.

Keep source-specific logic local to the source package. Do not reintroduce a shared top-level scraper registry.

Adding a new source should normally require:

1. a new `holocron/sources/<source>/source.py`
2. a new `holocron/sources/<source>/extract.py`
3. registration in `holocron/sources/__init__.py`
4. optional ClickHouse schema changes in `holocron/lib/sql/clickhouse_schema.sql`

If a change requires edits in many unrelated framework files, the architecture is probably drifting back toward over-engineering.

Small legacy/simple sources may still inline extraction in `source.py`, but new source-specific extraction code should still be split into `extract.py`.

## Dagster Modeling
- Keep one asset per durable ClickHouse table.
- Keep one local release asset per source.
- Keep one raw release asset per source.
- Express data quality as asset checks.
- Generate Dagster assets from source metadata rather than hand-writing per-table asset functions, except for clearly downstream derived assets.
- Model `SourceSpec.name` as the dataset / operational ingestion unit, not the whole provider.
- Use `SourceSpec.provider` for provider-level grouping in Dagster.
- Do not couple source ingest jobs to Dagster asset groups; jobs should target the source's explicit asset set.

## Naming
- Prefer short, recognizable dataset ids for sources: `pf_locations`, `dxbi_transactions`, `dld_od_rents`.
- Prefer provider-scoped warehouse table prefixes: `pf_*`, `dld_*`, `dxbi_*`, `dda_*`.
- For DDA planning data, use `dda_*` rather than `gis_*`; GIS is the data type, not the provider.

## Coding Conventions
- Match existing naming, formatting, file placement, and module boundaries before introducing a new pattern.
- Keep durable warehouse schema changes explicit in `holocron/lib/sql/clickhouse_schema.sql`.
- Use structured parsers or source-local helpers for extraction logic instead of broad shared scraping utilities.
- Do not commit generated build output, caches, local data, Docker volume state, or secrets.

## Testing
- Prefer targeted tests close to the changed behavior.
- Add or update tests when source contracts, extraction behavior, asset generation, data quality checks, or platform helpers change.
- Use `uv run pytest tests/<file>.py` for focused test runs when useful.
- Run `just check` before broad handoff when the change has meaningful blast radius.

## Commits And Reviews
- Use short, imperative Conventional Commit subjects when committing.
- In PR notes or handoffs, call out checks run and any checks intentionally skipped.
- If schemas, source contracts, asset keys, raw/local release behavior, credentials, or deploy workflows changed, call that out explicitly.

## Migration Note
Keep the repo Holocron-only. Do not reintroduce legacy package names or parallel orchestration stacks.
