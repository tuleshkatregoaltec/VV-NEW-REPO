## Development

We use `just` as the canonical command interface for local development. Run `just --list` to see the current recipes, and prefer those recipes over ad-hoc shell commands when setting up, running, checking, testing, building, migrating, or regenerating generated code.

Minimum runtime prerequisites for a fresh clone:

- `just`
- Docker Compose
- `uv`
- `bun`

Recommended host-side developer tooling:

- `prek`

Docker Compose gives every developer a reproducible local services environment. It is local-development-only infrastructure, not a production deployment definition.

The source of truth is the code in the host checkout. Frontend, backend, and Playwright run on the host by default. Docker Compose is for external services such as databases, auth, cache, object storage, and mail UI.

Environment file:

- [`.env.dev`](.env.dev) is the local runtime config for host app processes.
- The backend loads `.env.dev` by default in host mode.
- Keep local runtime URLs, ports, and local bootstrap credentials in `.env.dev`.

## Setup

Fresh clone quick start:

```sh
just setup
uv tool install prek
prek install
```

What these do:

- `just setup` installs frontend and e2e dependencies with Bun, installs the local Playwright Chromium browser, syncs the backend environment with `uv`, starts the local external services stack with Docker Compose, applies migrations, and seeds the local bootstrap admin with an active organization and subscription.
- `uv tool install prek` installs the Prek hook runner as a user-level `uv` tool.
- `prek install` enables this repo's git hooks locally.

Because `just setup` starts Docker Compose, Docker Desktop must already be running on macOS before setup.

## Running The App

For the usual split-terminal workflow:

```sh
just up
just dev-backend
just dev-frontend
```

For a single command that starts services and both host app processes:

```sh
just dev
```

Related app recipes:

- `just up` starts the Docker Compose service stack only.
- `just dev-backend` runs backend prestart work, then starts Uvicorn on the host.
- `just dev-frontend` starts the SvelteKit dev server on the host.
- `just dev-app` runs backend and frontend together when services are already running.
- `just dev` runs `just up`, then `just dev-app`.
- `just down` stops the Compose environment and removes local Compose volumes.
- `just ps` and `just logs` inspect the local Compose environment.

Main local endpoints:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Auth: `http://localhost:9999`
- Mail UI: `http://localhost:9000`
- MinIO console: `http://localhost:9003`

Local admin bootstrap:

- `just dev-backend` runs `backend/scripts/lifecycle/prestart.sh` before starting Uvicorn.
- The prestart script applies migrations and ensures the local bootstrap superuser exists.
- The default local bootstrap superuser credentials live in `.env.dev` via `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD`.

## Common Commands

Use `just --list` for the current command list. The main recipes are:

| Recipe | Purpose |
| --- | --- |
| `just setup` | Install host dependencies, start local services, apply migrations, and seed local bootstrap state. |
| `just up` | Start external services only. |
| `just down` | Stop services and remove local Compose volumes. |
| `just dev` | Start services, backend, and frontend for local development. |
| `just dev-app` | Start backend and frontend when services are already running. |
| `just dev-backend` | Start the FastAPI backend on the host. |
| `just dev-frontend` | Start the SvelteKit frontend on the host. |
| `just check-all` | Format backend/frontend, lint backend/frontend, then run backend/frontend tests. This may modify files. |
| `just test-backend` | Apply migrations and run backend tests. |
| `just test-frontend` | Run frontend unit tests. |
| `just test-e2e` | Run the Playwright e2e suite. |
| `just test-guards` | Run the mocked route-guard Playwright suite. |
| `just lint-backend` / `just format-backend` | Run backend Ruff checks or fixes. |
| `just lint-frontend` / `just format-frontend` | Run frontend Biome checks or formatting. |
| `just build-frontend` | Run the frontend production build. |
| `just generate-client` | Regenerate the frontend API types from the backend OpenAPI schema. |
| `just load-clickhouse-local` | Load local ClickHouse data and rebuild fact tables. |
| `just build-clickhouse-facts` | Rebuild local ClickHouse fact tables. |

Backend lifecycle scripts used by the recipes:

- `backend/scripts/lifecycle/prestart.sh`
- `backend/scripts/lifecycle/tests-start.sh`

## Checks And Tests

Tests, linting, formatting, and builds are run locally through `just`.

Useful verification pattern:

1. Run the narrowest target that covers your change.
2. Run broader checks when the blast radius justifies it.
3. Use `just check-all` before commits that touch both backend and frontend, shared contracts, generated code, or behavior with unclear boundaries.

Important details:

- `just check-all` is not read-only. It runs format recipes before linting and tests, so inspect `git diff` afterward and stage any intentional formatting changes.
- `just test-backend` applies migrations before running backend tests.
- Backend tests expect the local service stack to be available when tests need Postgres, auth, ClickHouse, Redis, or object storage.
- Playwright e2e tests expect local services and the backend to be available. The Playwright config can reuse a running frontend or start the frontend dev server for the test run.
- Use `just test-e2e` for real browser coverage and `just test-guards` for the mocked route-guard suite.

Generated client policy:

- Run `just generate-client` after changing backend routes, request schemas, or response schemas.
- The script generates `frontend/openapi.json`, runs the frontend OpenAPI generator, and keeps only the generated TypeScript types used by the hand-written frontend API layer.
- If generated types change, update the relevant files in `frontend/src/lib/api` and `frontend/src/lib/queries` in the same change.

## Git Hooks

Git hooks use Prek against the repo's [`.pre-commit-config.yaml`](.pre-commit-config.yaml). Install and enable them with:

```sh
uv tool install prek
prek install
```

By default, `prek` runs during `git commit`. To run the configured hooks across the whole repo manually:

```sh
prek run --all-files
```

Current hook behavior:

- Generic hooks check for large added files and merge conflicts.
- Generic whitespace and end-of-file hooks may rewrite files; when they do, review and stage the fixes before committing again.
- Backend and frontend lint hooks are selected based on staged file paths, but they run the repo's lint recipes rather than linting only the passed filenames.
- Hooks are host-driven and should not require Docker Compose.
- Tests and builds remain manual local commands rather than commit hooks.

If host `uv` commands fail with cache permission errors, repair ownership of `~/.cache/uv` and avoid running `uv` with `sudo`.

## Before Committing

Recommended commit checklist:

- Run a targeted check for the area you changed.
- Run `just up` before backend checks that need local services.
- Run `just check-all` for broad changes or when you want the standard local sweep.
- Inspect `git status` and `git diff` after `just check-all`, because formatting may have changed files.
- Run `just test-e2e` if your change touches auth flows, route guards, routing, browser-critical UI behavior, or cross-app flows.
- Make sure Prek hooks pass during commit.

When reporting checks in a PR or handoff, mention the meaningful checks run and any checks intentionally skipped.

## Cross-Platform Notes

The supported local workflow is host-first on Linux and macOS:

- App processes run on the host.
- Docker Compose runs local dependencies.
- Playwright runs on the host and targets local app URLs.

### macOS Prerequisites

Install prerequisites via [Homebrew](https://brew.sh). If Homebrew is not installed:

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install Xcode command-line tools, which are required for native build dependencies:

```sh
xcode-select --install
```

Install runtime prerequisites:

```sh
brew install just
brew install uv
brew install oven-sh/bun/bun
```

Install Docker Desktop from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop). Docker Compose is bundled with Docker Desktop. Docker Desktop must be open and running before `just setup`, `just up`, or `just dev`.

After prerequisites are installed:

```sh
just setup
uv tool install prek
prek install
```

Follow any post-install instructions that `brew` prints for `uv` and `bun`; they may require shell profile updates such as entries in `~/.zshrc`.

## Deployment Notes

Production deployment is separate from the local Compose environment:

- The frontend production build is for Cloudflare Pages with environment variables injected by that platform.
- The backend production image is built from `backend/Dockerfile`.
- Managed production services such as databases, caches, and object storage are external and are not provisioned by this repo.
