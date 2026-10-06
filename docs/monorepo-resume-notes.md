# Monorepo Resume Notes

Date: 2026-06-10
Branch: `monorepo/holocron-import`

## Goal

Move `holocron` into the Vitevue platform repo as a separate root package while
keeping runtime boundaries clear:

- frontend remains Cloudflare Pages
- backend runs separately
- Holocron remains its own pipeline runtime
- databases/Redis/object storage are shared infrastructure, not shared process
  runtime

## Completed Checkpoints

Recent commits:

- `bd139e6` docs: document monorepo migration preflight
- `3283bd7` chore: import holocron subtree
- `51416a8` chore: add holocron command delegate
- `55139a1` chore: consolidate environment examples
- `d495c70` chore: standardize environment variables
- `62bc272` chore: use provider-neutral object storage config

Important completed work:

- Imported Holocron at repo root as `holocron/`, preserving history with a
  subtree import.
- Added root `just holocron ...` delegation.
- Added backend `.dockerignore` coverage so backend build context does not carry
  the pipeline tree.
- Consolidated env docs in `docs/env-audit.md`.
- Standardized ClickHouse naming around `CLICKHOUSE_DATABASE`.
- Added `CLICKHOUSE_SECURE`.
- Split native ClickHouse port use to `CLICKHOUSE_NATIVE_PORT` for
  `clickhouse-driver` scripts only.
- Replaced provider-specific object storage envs with `OBJECT_STORAGE_*`.
- Renamed storage wrappers from S3/R2 names to provider-neutral names:
  `ObjectStorageClient`, `ObjectStorageResource`, and `object_storage` modules.

## Current Environment Standard

Object storage canonical env vars:

- `OBJECT_STORAGE_PROVIDER`
- `OBJECT_STORAGE_ENDPOINT_URL`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `OBJECT_STORAGE_BUCKET`
- `OBJECT_STORAGE_REGION`
- `OBJECT_STORAGE_USE_PATH_STYLE`
- `OBJECT_STORAGE_PUBLIC_URL_BASE`

Current provider is `r2`. Future-supported provider values are `aws_s3` and
`minio`. `OBJECT_STORAGE_ENDPOINT_URL` is required for `r2` and `minio`; it can
be unset for native AWS S3.

ClickHouse canonical env vars:

- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_NATIVE_PORT`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_SECURE`

Postgres roles:

- `DATABASE_URL`: backend app database
- `DAGSTER_POSTGRES_URL`: Dagster metadata database
- `PLATFORM_POSTGRES_URL`: app database URL used by Holocron publishing jobs

## Intentional Deferrals

These are deliberately not changed yet because they are data/API contracts, not
just runtime config:

- manifest fields such as `s3_key` and `manifest_s3_key`
- ClickHouse provenance columns such as `raw_manifest_s3_key`
- upload health API field `s3`
- script filename `backend/scripts/news/import_from_s3.py`

Boto/aioboto SDK boundary names also remain because they are library API names:

- `aws_access_key_id`
- `aws_secret_access_key`
- `session.client("s3")`
- `Config(s3=...)`

## Validation Already Run

After the latest object-storage checkpoint:

- backend focused `ruff check`
- backend settings smoke test with `OBJECT_STORAGE_PROVIDER=r2`
- backend settings smoke test with `OBJECT_STORAGE_PROVIDER=aws_s3` and no
  endpoint
- backend failure check for `OBJECT_STORAGE_PROVIDER=r2` without endpoint
- Holocron doctor provider checks
- `docker compose config --services`
- `just holocron doctor local`
- `just holocron check`

Holocron full check passed with 226 tests.

## Next Recommended Steps

1. Update real deployment/Bitwarden secret names from the previous storage names
   to `OBJECT_STORAGE_*`. This is intentionally a breaking rename with no legacy
   aliases.
2. Clean up justfiles:
   - define a smaller root command taxonomy
   - keep package-specific detail inside each package
   - reduce overlap between root and Holocron commands
   - ~~decide whether `r2` remains the target name or becomes `raw-test`~~ → renamed to `raw-test`
3. Audit Docker Compose files:
   - root Compose should contain only local platform dependencies
   - Holocron Compose should contain only Dagster/pipeline runtime concerns
   - decide whether duplicate local Postgres/ClickHouse/MinIO services are still
     needed in both stacks
   - remove or rename stale tunnel/raw-test files only after confirming purpose
4. Decide separately whether to migrate persisted `*_s3_key` names to
   `*_object_key`. That should be its own migration with ClickHouse/schema/test
   coverage.

## Current State

Worktree was clean after commit `62bc272` before this note was added.
