#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env"
FORCE=0
RAW_ONLY=0
BWS_IMAGE="${BWS_IMAGE:-ghcr.io/bitwarden/bws}"
BWS_PROJECT_ID="${BWS_PROJECT_ID:-}"

usage() {
  cat <<'USAGE'
Usage: scripts/pull-bitwarden-env.sh [--env-file PATH] [--project-id UUID] [--force] [--raw-only]

Pull Holocron VPS environment variables from Bitwarden Secrets Manager and write
them to .env. Requires:

  BWS_ACCESS_TOKEN   Bitwarden Secrets Manager machine account access token
  BWS_PROJECT_ID     Bitwarden Secrets Manager project id, unless --project-id is passed

The script uses the official bws Docker image, so the host only needs Docker.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="${2:?--env-file requires a path}"
      shift 2
      ;;
    --project-id)
      BWS_PROJECT_ID="${2:?--project-id requires a project id}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --raw-only)
      RAW_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${BWS_ACCESS_TOKEN:-}" ]]; then
  echo "BWS_ACCESS_TOKEN is required." >&2
  exit 2
fi

if [[ -z "${BWS_PROJECT_ID:-}" ]]; then
  echo "BWS_PROJECT_ID is required. Pass --project-id or export BWS_PROJECT_ID." >&2
  exit 2
fi

if [[ -e "$ENV_FILE" && "$FORCE" != "1" ]]; then
  echo "$ENV_FILE already exists. Re-run with --force to overwrite it." >&2
  exit 2
fi

TMP_FILE="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
trap 'rm -f "$TMP_FILE"' EXIT

docker run --rm \
  -e BWS_ACCESS_TOKEN \
  "$BWS_IMAGE" \
  secret list "$BWS_PROJECT_ID" --output env --color no > "$TMP_FILE"

if [[ ! -s "$TMP_FILE" ]]; then
  echo "Bitwarden returned no secrets for project $BWS_PROJECT_ID." >&2
  exit 1
fi

if grep -q "commented-out due to a problematic key name" "$TMP_FILE"; then
  echo "Bitwarden reported one or more non-POSIX secret keys. Fix the key names first." >&2
  exit 1
fi

PROD_REQUIRED_KEYS=(
  CLICKHOUSE_HOST
  CLICKHOUSE_USER
  CLICKHOUSE_PASSWORD
  OBJECT_STORAGE_ACCESS_KEY_ID
  OBJECT_STORAGE_SECRET_ACCESS_KEY
  OBJECT_STORAGE_BUCKET
  OBJECT_STORAGE_ENDPOINT_URL
)

RAW_REQUIRED_KEYS=(
  OBJECT_STORAGE_ACCESS_KEY_ID
  OBJECT_STORAGE_SECRET_ACCESS_KEY
  OBJECT_STORAGE_BUCKET
  OBJECT_STORAGE_ENDPOINT_URL
)

EXPECTED_KEYS=(
  CLICKHOUSE_HOST
  CLICKHOUSE_USER
  CLICKHOUSE_PASSWORD
  OBJECT_STORAGE_ACCESS_KEY_ID
  OBJECT_STORAGE_SECRET_ACCESS_KEY
  OBJECT_STORAGE_BUCKET
  OBJECT_STORAGE_ENDPOINT_URL
  OBJECT_STORAGE_PUBLIC_URL_BASE
  BAYUT_API_KEY
  REELLY_EMAIL
  REELLY_PASSWORD
  TWOCAPTCHA_API_KEY
  PLATFORM_POSTGRES_URL
  NEWS_FEED_URLS
)

REQUIRED_KEYS=("${PROD_REQUIRED_KEYS[@]}")
if [[ "$RAW_ONLY" == "1" ]]; then
  REQUIRED_KEYS=("${RAW_REQUIRED_KEYS[@]}")
fi

MISSING_REQUIRED=()
for key in "${REQUIRED_KEYS[@]}"; do
  if ! grep -Eq "^${key}=" "$TMP_FILE" || grep -Eq "^${key}=\"\"$" "$TMP_FILE"; then
    MISSING_REQUIRED+=("$key")
  fi
done

if (( ${#MISSING_REQUIRED[@]} > 0 )); then
  printf 'Missing required Bitwarden secrets: %s\n' "${MISSING_REQUIRED[*]}" >&2
  exit 1
fi

MISSING_EXPECTED=()
for key in "${EXPECTED_KEYS[@]}"; do
  if ! grep -Eq "^${key}=" "$TMP_FILE"; then
    MISSING_EXPECTED+=("$key")
  fi
done

if (( ${#MISSING_EXPECTED[@]} > 0 )); then
  printf 'Warning: expected optional keys are not present: %s\n' "${MISSING_EXPECTED[*]}" >&2
fi

if grep -Eq "^BWS_ACCESS_TOKEN=" "$TMP_FILE"; then
  echo "Refusing to write BWS_ACCESS_TOKEN to $ENV_FILE. Do not store it in the Holocron project." >&2
  exit 1
fi

chmod 600 "$TMP_FILE"
mv "$TMP_FILE" "$ENV_FILE"
trap - EXIT

echo "Wrote $ENV_FILE from Bitwarden project $BWS_PROJECT_ID."
