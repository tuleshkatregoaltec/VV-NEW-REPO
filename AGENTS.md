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
This repo combines a FastAPI backend, a SvelteKit frontend, and Playwright browser tests.

- Backend domains live under `backend/app`; keep new code inside the relevant domain unless it is genuinely shared.
- Frontend app code lives under `frontend/src`; shared utilities and components belong in `frontend/src/lib`, while route entries stay in `frontend/src/routes`.
- Backend tests live under `backend/tests`; frontend unit tests live under `frontend/tests`; cross-app browser tests live under `e2e`.
- Database migrations live under `backend/migrations`.

## Stack And Tooling
- Backend: FastAPI, SQLModel, Alembic, PostgreSQL, Redis, ClickHouse.
- Frontend: SvelteKit, Vite, Bun, Tailwind, Biome.
- Browser testing: Playwright.
- Local development runs app processes on the host and external services through Docker Compose.
- `just` is the canonical command interface. Use `just --list` and `development.md` to discover setup, dev, lint, format, test, build, migration, and generated-client workflows instead of inventing ad-hoc commands.

## Platform Notes
This repo is developed on Linux and macOS. On macOS, use Homebrew for CLI prerequisites and Docker Desktop for Docker Compose. Do not suggest `apt` or `snap` commands to macOS users.

## Core Workflow
- Follow `development.md` for setup, local environment separation, running the app, and commit checks.
- Use `.env.dev` for host-run app processes.
- Treat Docker Compose as local external services only, not the production runtime model.
- Prefer host tooling for source-code tasks such as linting, formatting, tests, code generation, and git hooks.

## Coding Conventions
- Match existing naming, formatting, and file placement before introducing a new pattern.
- Keep Svelte components in `PascalCase`, stores/utilities in `camelCase`, and route folders aligned with URL paths.
- Use Ruff-compatible Python style: `snake_case` for modules/functions and `PascalCase` for classes.
- Keep domain-specific ClickHouse SQL in the owning domain. Shared ClickHouse helpers belong in `backend/app/clickhouse`.
- Do not commit secrets, generated build output, local data, or Docker volume state.

## Feature Development
Follow the existing layer boundaries. Do not move business logic into route handlers or page components just because it is faster.

Backend features usually flow through:
1. `backend/app/{domain}/models.py` for request/response schemas.
2. `backend/app/{domain}/service.py` for business logic and data access.
3. `backend/app/{domain}/router.py` for thin FastAPI endpoints and auth guards.
4. `backend/app/main.py` for router registration.
5. `backend/migrations/` when PostgreSQL schema changes.

Frontend features usually flow through:
1. Regenerate the API client after backend schema changes.
2. Add typed API wrappers in `frontend/src/lib/api`.
3. Add TanStack Query keys and query builders in `frontend/src/lib/queries`.
4. Add stores only for cross-component state that cannot stay local.
5. Add feature components under `frontend/src/lib/components`.
6. Keep route files in `frontend/src/routes` thin and focused on composition.

## API And Query Patterns
- Frontend code should call typed API helpers, not raw endpoints directly from components or routes.
- Query keys and query builders belong in `frontend/src/lib/queries`; avoid ad-hoc keys in component code.
- Keep API contracts canonical. Do not add frontend-only request shapes when explicit backend fields already express the filter or operation.
- When backend schemas change, regenerate the frontend client and update related API/query helpers together.

## Testing
- Prefer targeted tests close to the changed behavior.
- Add backend route tests for API behavior and backend unit tests for business logic.
- Add frontend unit tests for meaningful component or query behavior.
- Add or update Playwright tests when user flows, auth boundaries, routing, or guarded pages change.
- Run the narrowest useful `just` check first, then broader checks when the change warrants it.

## Commits And Reviews
- Use short, imperative Conventional Commit subjects when committing.
- In PR notes or handoffs, mention the meaningful checks run and any checks intentionally skipped.
- If auth, billing, data access, migrations, generated clients, or guarded flows changed, call that out explicitly.
