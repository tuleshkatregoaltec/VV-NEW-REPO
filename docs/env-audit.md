# Environment Variable Standard

Date: 2026-06-10

## Scope

This document records the monorepo environment variable standard after importing
`holocron/`. It covers backend, frontend, E2E, Holocron, Compose, and env
generation scripts.

No local secret values were inspected.

## Naming Rules

- Use service prefixes for infrastructure-specific config: `OBJECT_STORAGE_*`,
  `CLICKHOUSE_*`, `DAGSTER_*`, `PLAYWRIGHT_*`.
- Use product/runtime names for app concepts: `DATABASE_URL`, `FRONTEND_URL`,
  `PLATFORM_POSTGRES_URL`.
- Do not carry legacy aliases in code. Rename call sites and env files together.
- Use provider-neutral object-storage naming. The current production provider
  value is `r2`, but the env contract should also work for AWS S3 or MinIO.
- Docker image-specific env names may still appear inside Compose service
  `environment` blocks when required by the upstream image. Those names are not
  application runtime config.

## Shared Infrastructure

### Object Storage

Canonical object-storage env vars:

- `OBJECT_STORAGE_PROVIDER`
- `OBJECT_STORAGE_ENDPOINT_URL`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `OBJECT_STORAGE_BUCKET`
- `OBJECT_STORAGE_REGION`
- `OBJECT_STORAGE_USE_PATH_STYLE`
- `OBJECT_STORAGE_PUBLIC_URL_BASE`

`OBJECT_STORAGE_PROVIDER` currently accepts `r2`, `aws_s3`, or `minio`.
`OBJECT_STORAGE_ENDPOINT_URL` is required for `r2` and `minio`; leave it unset
for native AWS S3 unless a custom endpoint is needed.
`OBJECT_STORAGE_PUBLIC_URL_BASE` is only needed when Holocron should write
public asset URLs into inventories. Backend thumbnail serving signs private
object keys through the API and does not require this value.

Local MinIO can still be used for development by setting these same
`OBJECT_STORAGE_*` vars to MinIO endpoint and credentials.

### ClickHouse

Canonical application env vars:

- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_NATIVE_PORT`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_SECURE`

`CLICKHOUSE_PORT` is the HTTP/HTTPS port used by `clickhouse-connect`.
`CLICKHOUSE_NATIVE_PORT` is only for scripts that use `clickhouse-driver`.

Compose maps `CLICKHOUSE_DATABASE` into the upstream ClickHouse image's required
database bootstrap key.

### Postgres

Canonical Postgres env vars:

- `DATABASE_URL`: backend app database.
- `DAGSTER_POSTGRES_URL`: Dagster run/event/schedule metadata.
- `PLATFORM_POSTGRES_URL`: app database URL used by Holocron publishing jobs.

These are intentionally separate even when they may point at databases on the
same server.

### Redis

Canonical Redis env vars:

- `REDIS_URL`
- `REDIS_PASSWORD`

Redis is currently backend-only.

## Runtime Owners

### Backend

Required backend settings:

- `DATABASE_URL`
- `REDIS_URL`
- `REDIS_PASSWORD`
- `FRONTEND_URL`
- `SESSION_SECRET`
- `SERVICE_API_KEY`
- `AUTH_URL`
- `AUTH_SERVICE_ROLE_KEY`
- `OPENROUTER_API_KEY`
- `DEFAULT_CHAT_MODEL`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `OBJECT_STORAGE_BUCKET`
- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_DATABASE`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_TIER1`
- `STRIPE_PRICE_ID_TIER2`
- `FRONTEND_SUCCESS_URL`
- `FRONTEND_CANCEL_URL`

Optional backend settings:

- `ENVIRONMENT`
- `PUBLIC_API_BASE_URL`
- `ALLOWED_ORIGINS`
- `OBJECT_STORAGE_PROVIDER`
- `OBJECT_STORAGE_ENDPOINT_URL`
- `OBJECT_STORAGE_REGION`
- `OBJECT_STORAGE_USE_PATH_STYLE`
- `CLICKHOUSE_SECURE`
- `LOGFIRE_TOKEN`
- `HONEYBADGER_API_KEY`
- `POSTHOG_API_KEY`
- `POSTHOG_HOST`
- `FIRST_SUPERUSER`
- `FIRST_SUPERUSER_PASSWORD`
- `FIRST_SUPERUSER_RENAME_FROM`
- `FIRST_SUPERUSER_FIRST_NAME`
- `FIRST_SUPERUSER_LAST_NAME`
- `FIRST_SUPERUSER_AVATAR_URL`

Backend script-only settings:

- `CLICKHOUSE_NATIVE_PORT`

Backend settings with defaults that do not need to appear in every env file:

- `API_V1_STR`
- `PROJECT_NAME`

### Frontend

Frontend browser-exposed env vars:

- `PUBLIC_API_BASE_URL`
- `PUBLIC_AUTH_BASE_URL`
- `PUBLIC_POSTHOG_HOST`
- `PUBLIC_POSTHOG_KEY`

### E2E

Optional Playwright env vars:

- `PLAYWRIGHT_BASE_URL`
- `PLAYWRIGHT_API_BASE_URL`
- `PLAYWRIGHT_AUTH_BASE_URL`
- `PLAYWRIGHT_INBUCKET_BASE_URL`
- `TEST_EMAIL`
- `TEST_PASSWORD`
- `FIRST_SUPERUSER`
- `FIRST_SUPERUSER_PASSWORD`
- `CI`

### Holocron

Required for full Holocron production:

- `DAGSTER_POSTGRES_URL`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `OBJECT_STORAGE_REGION`
- `OBJECT_STORAGE_BUCKET`
- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_SECURE`

Required for raw-only object-storage smoke tests:

- `DAGSTER_POSTGRES_URL`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `OBJECT_STORAGE_REGION`
- `OBJECT_STORAGE_BUCKET`

Optional Holocron settings:

- `DAGSTER_PORT`
- `OBJECT_STORAGE_PROVIDER`
- `OBJECT_STORAGE_ENDPOINT_URL`
- `OBJECT_STORAGE_USE_PATH_STYLE`
- `OBJECT_STORAGE_PUBLIC_URL_BASE`
- `REELLY_EMAIL`
- `REELLY_PASSWORD`
- `TWOCAPTCHA_API_KEY`
- `CAPTCHA_API_KEY`
- `PLATFORM_POSTGRES_URL`
- `NEWS_FEED_URLS`
- `NEWS_THUMBNAIL_PREFIX`
- `HOLOCRON_SCRATCH_DIR`

## Removed Stale Names

Do not reintroduce legacy object-storage names from earlier providers, old
Cloudflare R2 endpoint aliases, the old backend ClickHouse database alias, or
historical unused auth, OpenRouter, Stripe, contact, and Bayut settings. Add any
new env var to this document and the relevant `.env.example` file in the same
change that introduces it.

## Notes

- Backend code now reads `CLICKHOUSE_DATABASE` directly. Legacy database aliases
  are not supported backend settings.
- Backend and Holocron both read object storage through `OBJECT_STORAGE_*` vars
  only.
- Holocron news thumbnail prefixes use `media/news/thumbnails`, matching backend
  thumbnail proxy detection.
