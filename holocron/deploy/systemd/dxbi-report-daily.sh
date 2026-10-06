#!/usr/bin/env bash
set -euo pipefail

report="${1:-}"
cadence="${2:-daily}"
case "$report" in
  rentals)
    account="b"
    ;;
  sales)
    account="a"
    ;;
  *)
    echo "usage: $0 rentals|sales" >&2
    exit 64
    ;;
esac
case "$cadence" in
  daily|weekly|monthly)
    ;;
  *)
    echo "usage: $0 rentals|sales [daily|weekly|monthly]" >&2
    exit 64
    ;;
esac
if [[ "$report" == "sales" && "$cadence" != "daily" ]]; then
  echo "sales supports the daily cadence only" >&2
  exit 64
fi

repo_dir="${DXBI_REPO_DIR:-/root/repos/vitevue-platform}"
data_dir="${DXBI_DAILY_DATA_DIR:-/root/data/dxbi-daily}"
config_dir="${DXBI_CONFIG_DIR:-/root/.config/vitevue/dxbi}"
browser="${DXBI_BROWSER:-/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome}"
# Use Dubai's calendar date even though the server clock is UTC. Rental windows
# overlap by design so registrations arriving as late as a year are revisited.
run_date="$(TZ=Asia/Dubai date +%F)"
case "$report:$cadence" in
  rentals:daily)
    start_offset=14
    end_offset=0
    timeout_duration="${DXBI_DAILY_TIMEOUT:-3h}"
    ;;
  rentals:weekly)
    start_offset=180
    end_offset=15
    timeout_duration="${DXBI_WEEKLY_TIMEOUT:-12h}"
    ;;
  rentals:monthly)
    start_offset=365
    end_offset=181
    timeout_duration="${DXBI_MONTHLY_TIMEOUT:-24h}"
    ;;
  *)
    start_offset="${DXBI_SALES_LOOKBACK_DAYS:-7}"
    end_offset=0
    timeout_duration="${DXBI_DAILY_TIMEOUT:-3h}"
    ;;
esac
start_date="$(TZ=Asia/Dubai date -d "${run_date} - ${start_offset} days" +%F)"
end_date="$(TZ=Asia/Dubai date -d "${run_date} - ${end_offset} days" +%F)"
template_date="$(TZ=Asia/Dubai date -d "${run_date} - 1 day" +%F)"
output_dir="${data_dir}/${report}/run=${run_date}-${cadence}"
lock_file="/run/lock/vitevue-dxbi-${report}.lock"

mkdir -p "$output_dir"
record_failure() {
  exit_code=$?
  trap - EXIT
  if (( exit_code != 0 )) && [[ ! -f "${output_dir}/_SUCCESS" ]]; then
    failure_tmp="${output_dir}/_FAILURE.tmp.$$"
    printf '{"status":"failed","exit_code":%d,"failed_at":"%s"}\n' \
      "$exit_code" "$(date -u +%FT%TZ)" > "$failure_tmp"
    mv "$failure_tmp" "${output_dir}/_FAILURE"
  fi
  exit "$exit_code"
}
trap record_failure EXIT
exec 9>"$lock_file"
echo "Waiting for the shared ${report} scrape lock."
flock 9

manifest_args=()
if [[ "$report" == "rentals" ]]; then
  manifest_path="${DXBI_RENTAL_MANIFEST:-${config_dir}/rental-profile-manifest.json}"
  if [[ ! -f "$manifest_path" ]]; then
    echo "Rental profile manifest is missing: ${manifest_path}" >&2
    exit 1
  fi
  manifest_args=(--manifest-path "$manifest_path" --verify-manifest)
fi

/usr/bin/timeout --signal=TERM --kill-after=30s "$timeout_duration" \
  "${repo_dir}/holocron/.venv/bin/python" \
  "${repo_dir}/holocron/scripts/dxbi_rental_backfill.py" \
  --credentials "${config_dir}/account-${account}.json" \
  --storage-state "${config_dir}/account-${account}-state.json" \
  --browser "$browser" \
  --output-dir "$output_dir" \
  --start-date "$start_date" \
  --end-date "$end_date" \
  --direction desc \
  --template-date "$template_date" \
  --delay-min 2 \
  --delay-max 4 \
  --report "$report" \
  --account-id "account-${account}" \
  --run-id "${run_date}-${cadence}" \
  "${manifest_args[@]}"

if [[ ! -f "${output_dir}/_SUCCESS" ]]; then
  echo "${report} ${cadence} scrape exited without a terminal success marker" >&2
  exit 1
fi
