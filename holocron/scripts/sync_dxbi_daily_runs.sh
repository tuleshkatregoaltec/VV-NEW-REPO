#!/usr/bin/env bash
set -euo pipefail

repo_dir="${VITEVUE_REPO_DIR:-/Users/eier/VV/vitevue-platform-full-platform}"
sync_dir="${DXBI_SYNC_DIR:-/Users/eier/VV/DXBI-Daily}"
remote="${DXBI_REMOTE:-root@188.245.147.179}"
remote_dir="${DXBI_REMOTE_DIR:-/root/data/dxbi-daily/}"
loaded_dir="${sync_dir}/.loaded"
sync_attempts="${DXBI_SYNC_ATTEMPTS:-5}"
sync_retry_delay_seconds="${DXBI_SYNC_RETRY_DELAY_SECONDS:-30}"
clickhouse_ready_attempts="${DXBI_CLICKHOUSE_READY_ATTEMPTS:-20}"
clickhouse_retry_delay_seconds="${DXBI_CLICKHOUSE_RETRY_DELAY_SECONDS:-15}"

mkdir -p "$sync_dir" "$loaded_dir"
if [[ "${DXBI_LOCK_HELD:-}" != "1" ]]; then
  export PYTHONPATH="${repo_dir}/holocron"
  exec "${repo_dir}/holocron/.venv/bin/python" -m holocron.platform.run_locked \
    "${sync_dir}/sync.lock" /usr/bin/env DXBI_LOCK_HELD=1 /bin/bash "$0"
fi

for ((attempt = 1; attempt <= sync_attempts; attempt++)); do
  if rsync -az --partial -e "ssh -o BatchMode=yes" "$remote:$remote_dir" "$sync_dir/"; then
    break
  fi
  if (( attempt == sync_attempts )); then
    echo "DXBI sync failed after ${sync_attempts} attempts." >&2
    exit 1
  fi
  echo "DXBI sync attempt ${attempt} failed; retrying in ${sync_retry_delay_seconds}s." >&2
  sleep "$sync_retry_delay_seconds"
done

health_status=0
for report in rentals sales; do
  recent_success="$(find "${sync_dir}/${report}" \
    -mindepth 2 -maxdepth 2 -type f \
    \( -path '*/run=????-??-??/_SUCCESS' -o -path '*/run=????-??-??-daily/_SUCCESS' \) \
    -mmin -2160 -print -quit 2>/dev/null)"
  if [[ -z "$recent_success" ]]; then
    echo "DXBI ${report} health failure: no successful daily run in the last 36 hours." >&2
    health_status=1
  fi
done

rental_runs=()
sales_runs=()
while IFS= read -r run_dir; do
  run_name="${run_dir##*/}"
  if [[ -f "${run_dir}/_SUCCESS" && ! -f "${loaded_dir}/rentals-${run_name}" ]]; then
    rental_runs+=("$run_dir")
  fi
done < <(find "${sync_dir}/rentals" -mindepth 1 -maxdepth 1 -type d -name 'run=*' 2>/dev/null | sort)
while IFS= read -r run_dir; do
  run_name="${run_dir##*/}"
  if [[ -f "${run_dir}/_SUCCESS" && ! -f "${loaded_dir}/sales-${run_name}" ]]; then
    sales_runs+=("$run_dir")
  fi
done < <(find "${sync_dir}/sales" -mindepth 1 -maxdepth 1 -type d -name 'run=*' 2>/dev/null | sort)

geography_pending="${loaded_dir}/geography-pending"
if (( ${#rental_runs[@]} == 0 && ${#sales_runs[@]} == 0 )) && [[ ! -f "$geography_pending" ]]; then
  echo "No new completed DXBI runs to load."
  exit "$health_status"
fi

set -a
# shellcheck disable=SC1091
source "${repo_dir}/.env.dev"
set +a
export PYTHONPATH="${repo_dir}/holocron"

for ((attempt = 1; attempt <= clickhouse_ready_attempts; attempt++)); do
  if (exec 3<>"/dev/tcp/${CLICKHOUSE_HOST}/${CLICKHOUSE_PORT}") 2>/dev/null; then
    break
  fi
  if (( attempt == clickhouse_ready_attempts )); then
    echo "ClickHouse was unavailable after ${clickhouse_ready_attempts} attempts." >&2
    exit 1
  fi
  echo "ClickHouse is unavailable; retrying in ${clickhouse_retry_delay_seconds}s." >&2
  sleep "$clickhouse_retry_delay_seconds"
done

cd "${repo_dir}/holocron"
if (( ${#rental_runs[@]} > 0 )); then
  rental_load_id="$(date -u +%Y%m%dT%H%M%SZ)"
  .venv/bin/python scripts/load_dxbi_rental_events.py \
    --target active \
    --host "$CLICKHOUSE_HOST" \
    --port "$CLICKHOUSE_PORT" \
    --database "$CLICKHOUSE_DATABASE" \
    --username "$CLICKHOUSE_USER" \
    --password "$CLICKHOUSE_PASSWORD" \
    --run-id "$rental_load_id" \
    --reconciliation-output "${loaded_dir}/rentals-${rental_load_id}.json" \
    "${rental_runs[@]}"
  for run_dir in "${rental_runs[@]}"; do
    touch "${loaded_dir}/rentals-${run_dir##*/}"
  done
  touch "$geography_pending"
fi
if (( ${#sales_runs[@]} > 0 )); then
  .venv/bin/python scripts/load_dxbi_sales_units.py \
    --host "$CLICKHOUSE_HOST" \
    --port "$CLICKHOUSE_PORT" \
    --database "$CLICKHOUSE_DATABASE" \
    --username "$CLICKHOUSE_USER" \
    --password "$CLICKHOUSE_PASSWORD" \
    "${sales_runs[@]}"
  for run_dir in "${sales_runs[@]}"; do
    touch "${loaded_dir}/sales-${run_dir##*/}"
  done
  touch "$geography_pending"
fi

# Refresh the canonical location crosswalk after new report rows are loaded.
.venv/bin/python scripts/refresh_geography_crosswalk.py
rm -f "$geography_pending"
exit "$health_status"
