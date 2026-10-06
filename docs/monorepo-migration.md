# Monorepo Migration

Date: 2026-06-10

## Goal

Move `holocron` into the `vitevue-platform` repository as a root-level package and
deployable, while keeping runtime boundaries separate:

- `frontend/` deploys to Cloudflare Pages.
- `backend/` deploys to the backend server.
- `holocron/` deploys to the existing pipeline server.

The monorepo is a source-control and contract-management boundary, not a single
runtime unit.

## Target Layout

```text
vitevue-platform/
  backend/
  frontend/
  e2e/
  holocron/
  docs/
  scripts/
  justfile
```

Keep `holocron` self-contained at first, including its own `pyproject.toml`,
`uv.lock`, `Dockerfile`, `workspace.yaml`, `dagster.yaml`, compose files,
source package, tests, and docs.

## Current Repository State

- `vitevue-platform` is on `main`, synced with `origin/main`.
- `holocron` is on `main`, synced with `origin/main`.
- Both working trees were clean before this migration note was added.
- `vitevue-platform` remote: `ssh://github.com/vitevue/vitevue-platform`.
- `holocron` remote: `ssh://github.com/vitevue/holocron`.
- `vitevue-platform` has an `origin/production` branch used by the backend Docker
  publish workflow.
- `holocron` has no GitHub workflow files in the current checkout.
- `git subtree` is available and should be suitable for the history-preserving
  import.

## Existing Command Surface

`vitevue-platform` uses root `justfile` recipes:

- Setup/dev/services: `setup`, `up`, `down`, `logs`, `ps`, `dev`, `dev-app`,
  `dev-backend`, `dev-frontend`
- Backend: `test-backend`, `lint-backend`, `format-backend`
- Frontend: `test-frontend`, `build-frontend`, `lint-frontend`,
  `format-frontend`, `generate-client`
- E2E: `test-e2e`, `test-guards`
- ClickHouse helpers: `load-clickhouse-local`, `build-clickhouse-facts`,
  `import-mashrooi-radar-demo`

`holocron` uses its own root `justfile` recipes:

- Dev/checks: `sync`, `fmt`, `test`, `typecheck`, `check`
- Env/deploy/ops: `env`, `doctor`, `up`, `down`, `logs`, `ps`, `deploy`
- Data operations: `replay-bronze`, `dataset-version`

After import, preserve these commands by delegating from the monorepo root rather
than rewriting Holocron's internal workflow immediately.

## Current Deploy Artifacts

`vitevue-platform`:

- Backend production image is built from `backend/Dockerfile`.
- Existing GitHub workflow builds from repository root with `file:
  backend/Dockerfile`.
- Frontend is configured for Cloudflare Pages via SvelteKit Cloudflare adapter.
- Local Compose is development-only and starts Postgres, Supabase Auth, Inbucket,
  ClickHouse, Redis, and MinIO.

`holocron`:

- Production Compose is Dagster-only: `dagster-webserver` and `dagster-daemon`.
- Local Compose override adds local Postgres, ClickHouse, and MinIO.
- Dockerfile builds from the Holocron repository root and sets `DAGSTER_HOME=/app`.
- `workspace.yaml` loads `holocron.definitions`.

## Initial Migration Risks

- The backend Docker workflow currently sends the repository root as build
  context. After importing `holocron/`, update `.dockerignore` or the workflow
  so backend builds do not include the pipeline tree in the build context.
- `vitevue-platform` and `holocron` both rely on `docker compose`, but this local
  environment currently has Docker without the Compose plugin. Compose smoke
  tests could not be run here.
- `bun` is not installed in this local environment, so frontend build/test checks
  could not be run here.
- `holocron` docs include a migration note saying to keep that repo
  Holocron-only. After import, preserve the package boundary and update that
  instruction so it applies to `holocron/` within the monorepo.
- Environment variable names have been standardized across packages. Application
  code should use `CLICKHOUSE_DATABASE` for ClickHouse and `OBJECT_STORAGE_*`
  for provider-neutral object storage. Compose may still map
  `CLICKHOUSE_DATABASE` into image-specific variables required by upstream
  containers.
- The backend owns app PostgreSQL schema through SQLModel/Alembic. Holocron owns
  ClickHouse bronze DDL. Keep those ownership lines intact.

## Next Checkpoint

Before importing files:

1. Create a migration branch in `vitevue-platform`.
2. Choose the exact subtree command for importing `holocron` into root
   `holocron/`.
3. Decide whether the initial import commit should be history-preserving full
   subtree history or a squashed import. Prefer full history unless repository
   policy says otherwise.
4. Identify the minimal path changes needed after import.
