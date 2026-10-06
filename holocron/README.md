# Holocron

Holocron is being rebuilt from first principles as a small connector platform.

Current scope:

- source contracts
- immutable raw release manifests
- shared R2-compatible object storage and ClickHouse clients
- source registry
- thin Dagster definitions

## Architecture

The intended flow is:

```text
source connector
  -> immutable raw release in Cloudflare R2
  -> current raw-shaped bronze ClickHouse tables
  -> optional domain outputs
```

Dagster is the control plane around those assets, not the place where source logic lives.

## Setup

The repo now ships with a `justfile` so the local and VPS workflows stay aligned.

Common commands:

- `just sync` installs Python dependencies with `uv`
- `just check` runs format, lint, and tests
- `just env local` creates `.env.local` from `.env.local.example`
- `just env prod` writes `.env` from Bitwarden Secrets Manager
- `just env prod-manual` creates `.env` from `.env.example`
- `just env raw-test` creates `.env.raw-test` from `.env.raw-test.example`
- `just up <target>` starts a stack; targets are `local`, `prod`, or `raw-test`
- `just down <target>`, `just ps <target>`, and `just logs <target>` operate a stack
- `just deploy` pulls the latest code and rebuilds the VPS stack

## VPS Flow

The production compose file is intentionally Dagster-only. A VPS should be disposable:

- raw releases and manifests live in Cloudflare R2
- bronze warehouse tables live in external ClickHouse
- Dagster run/event/schedule metadata lives in external Postgres
- the VPS runs only `dagster-webserver` and `dagster-daemon`

Fresh VPS bootstrap:

1. Install `docker`, Docker Compose, `git`, and `just`.
2. Clone the repo.
3. Export `BWS_ACCESS_TOKEN` and `BWS_PROJECT_ID` for the Holocron Bitwarden
   Secrets Manager project.
4. Run `just env prod`.
5. Run `just doctor prod`.
6. Run `just up prod`.

For manual setup without Bitwarden, run `just env prod-manual` and fill in `.env` from
`.env.example`.

After that, Dagster is available on `http://<vps-ip>:3000` unless `DAGSTER_PORT`
is changed.

To move VPSs, stop the old machine, clone the same repo on the new machine, put
the same Bitwarden machine account token and project id in the shell, then run
`just env prod --force` and `just up prod`. No ClickHouse or R2 data is
stored on the VPS.

For local development, use `docker-compose.local.yml` through `just up local`;
that override adds bind mounts plus local Postgres, ClickHouse, and MinIO.

### Raw Test Stack

Before production object storage, ClickHouse, and external Dagster Postgres are
ready, you can smoke-test raw extraction on a VPS with temporary local Postgres
for Dagster metadata:

```bash
just env raw-test
# fill .env.raw-test with object storage credentials and any source credentials needed
just up raw-test
```

If `BWS_ACCESS_TOKEN` and `BWS_PROJECT_ID` are exported, `just env raw-test`
pulls `.env.raw-test` from Bitwarden instead. The Bitwarden values should
include:

```text
DAGSTER_POSTGRES_URL=postgresql://dagster:dagster@postgres:5432/dagster
OBJECT_STORAGE_REGION=auto
OBJECT_STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
OBJECT_STORAGE_USE_PATH_STYLE=true
```

This starts only Dagster plus local Postgres. Raw releases and manifests are
written to object storage. Do not run bronze jobs in this mode unless
`.env.raw-test` has real ClickHouse values.

Useful commands:

```bash
just ps raw-test
just logs raw-test
just down raw-test
```

## Package Layout

```text
holocron/
  contracts.py
  definitions.py
  platform/
  sources/
  orchestration/
  domain/
```

- `contracts.py` defines the small core types.
- `platform/` holds shared infra.
- `sources/` holds the source registry and will hold source packages.
- `orchestration/` exposes Dagster definitions.
- `domain/` is reserved for cross-source outputs.

## Documentation

Raw ingestion standards and operational notes live under `docs/`:

- `docs/ingestion-patterns.md` defines chunked raw scrapes, asset hydration,
  R2 manifests, checkpoints, and source naming guidance.
- `docs/bronze-patterns.md` defines bronze loader structure, delete strategies,
  and ClickHouse schema conventions.
- `docs/logging.md` defines common progress and error logging expectations.
- `docs/scraping-investigation.md` is the playbook for new or fragile scrapers.
- `docs/runbooks/long-running-jobs.md` covers overnight job launch and status
  checks.

Most active source packages have a short `holocron/sources/<source>/README.md`
covering raw files, config knobs, R2 layout, and current limitations. The DLD
open-data endpoint packages share `holocron/sources/dld_open_data.md` because
they use one implementation and differ only by endpoint contract. Bronze lineage
docs are intentionally deferred until the raw source set is stable.

## Status

The current MVP focus is:

- source-local raw extraction into immutable releases
- bronze loading contracts per source
- thin Dagster orchestration around raw and bronze only

Recurring source jobs are wired to update bronze where the raw release is complete
enough to safely maintain current-state tables. Raw R2 manifests remain the
immutable audit/history layer.

Silver layers are intentionally deferred until a few sources are producing real
raw and bronze data and the cleaning requirements are clearer.

## News Feeds

News source details live in `holocron/sources/news_feeds/README.md`. Common
manual commands:

```bash
uv run dagster job execute -m holocron.definitions -j news_publish_backfill
uv run dagster job execute -m holocron.definitions -j news_thumbnail_assets_backfill
uv run dagster job execute -m holocron.definitions -j news_feeds_poll_and_hydrate
```
