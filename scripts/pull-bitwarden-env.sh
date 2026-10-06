#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env"
FORCE=0
BWS_IMAGE="${BWS_IMAGE:-ghcr.io/bitwarden/bws}"
BWS_PROJECT_ID="${BWS_PROJECT_ID:-}"

usage() {
  cat <<'USAGE'
Usage: scripts/pull-bitwarden-env.sh [--env-file PATH] [--project-id UUID] [--force]

Pull platform environment variables from Bitwarden Secrets Manager and write
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

# Keys required by the FastAPI backend (config.py). Missing or TO_BE_SET = hard fail.
REQUIRED_KEYS=(
  POSTGRES_URL
  REDIS_URL
  REDIS_PASSWORD
  SESSION_SECRET
  SERVICE_API_KEY
  AUTH_SERVICE_ROLE_KEY
  GOTRUE_JWT_SECRET
  OPENROUTER_API_KEY
  FRONTEND_URL
  FRONTEND_SUCCESS_URL
  FRONTEND_CANCEL_URL
  OBJECT_STORAGE_ENDPOINT_URL
  OBJECT_STORAGE_ACCESS_KEY_ID
  OBJECT_STORAGE_SECRET_ACCESS_KEY
  OBJECT_STORAGE_BUCKET
  CLICKHOUSE_PASSWORD
  STRIPE_SECRET_KEY
  STRIPE_WEBHOOK_SECRET
)

# Keys needed for a full Docker Compose deploy (auth service, migrations).
# Warn only — local dev without the auth container can skip these.
DEPLOYMENT_KEYS=(
  GOTRUE_DB_DATABASE_URL
  AUTH_DB_PASSWORD
  POSTGRES_USER
  POSTGRES_PASSWORD
  API_EXTERNAL_URL
  GOTRUE_SMTP_HOST
  GOTRUE_SMTP_USER
  GOTRUE_SMTP_PASS
  GOTRUE_SMTP_ADMIN_EMAIL
)

MISSING_REQUIRED=()
for key in "${REQUIRED_KEYS[@]}"; do
  if ! grep -Eq "^${key}=" "$TMP_FILE" || grep -Eq "^${key}=\"\"$" "$TMP_FILE"; then
    MISSING_REQUIRED+=("$key")
  elif grep -Eq "^${key}=\"TO_BE_SET\"$" "$TMP_FILE"; then
    MISSING_REQUIRED+=("$key (still set to TO_BE_SET)")
  fi
done

if (( ${#MISSING_REQUIRED[@]} > 0 )); then
  printf 'Missing or unfilled required Bitwarden secrets:\n' >&2
  printf '  %s\n' "${MISSING_REQUIRED[@]}" >&2
  exit 1
fi

MISSING_DEPLOYMENT=()
for key in "${DEPLOYMENT_KEYS[@]}"; do
  if ! grep -Eq "^${key}=" "$TMP_FILE" || grep -Eq "^${key}=\"TO_BE_SET\"$|^${key}=\"\"$" "$TMP_FILE"; then
    MISSING_DEPLOYMENT+=("$key")
  fi
done

if (( ${#MISSING_DEPLOYMENT[@]} > 0 )); then
  printf 'Warning: deployment-only keys missing (needed for full Docker Compose deploy): %s\n' "${MISSING_DEPLOYMENT[*]}" >&2
fi

if grep -Eq "^BWS_ACCESS_TOKEN=" "$TMP_FILE"; then
  echo "Refusing to write BWS_ACCESS_TOKEN to $ENV_FILE." >&2
  exit 1
fi

chmod 600 "$TMP_FILE"
mv "$TMP_FILE" "$ENV_FILE"
trap - EXIT

echo "Wrote $ENV_FILE from Bitwarden project $BWS_PROJECT_ID."
