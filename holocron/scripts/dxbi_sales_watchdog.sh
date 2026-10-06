#!/bin/zsh
set -u

SESSION_NAME="${DXBI_SALES_SESSION_NAME:-dxbi_sales_dynamic}"
SUPERVISOR="${DXBI_SALES_SUPERVISOR:-/Users/eier/VV/vitevue-platform-full-platform/holocron/scripts/dxbi_sales_dynamic_supervisor.sh}"
OUTPUT_DIR="${DXBI_SALES_OUTPUT_DIR:-/Users/eier/VV/DXBI-Backfill/sales-dynamic-full}"
STATE_PATH="${DXBI_SALES_STATE_PATH:-$OUTPUT_DIR/checkpoint.json}"
MONITOR_LOG="${DXBI_SALES_MONITOR_LOG:-$OUTPUT_DIR/monitor.log}"
CHECK_INTERVAL_SECONDS="${DXBI_SALES_MONITOR_INTERVAL_SECONDS:-120}"
STALL_SECONDS="${DXBI_SALES_STALL_SECONDS:-1200}"
ROW_STALL_SECONDS="${DXBI_SALES_ROW_STALL_SECONDS:-600}"
NO_RUNNER_SECONDS="${DXBI_SALES_NO_RUNNER_SECONDS:-180}"
LOCK_DIR="${DXBI_SALES_SUPERVISOR_LOCK_DIR:-$OUTPUT_DIR/supervisor.lock}"
WATCHDOG_LOCK_DIR="${DXBI_SALES_WATCHDOG_LOCK_DIR:-$OUTPUT_DIR/watchdog.lock}"

mkdir -p "$OUTPUT_DIR"

if ! mkdir "$WATCHDOG_LOCK_DIR" 2>/dev/null; then
  print -r -- "$(date -u '+%Y-%m-%dT%H:%M:%SZ') watchdog: another watchdog is already active; exiting" >> "$MONITOR_LOG"
  exit 0
fi

print -r -- "$$" > "$WATCHDOG_LOCK_DIR/pid"

cleanup_watchdog() {
  rm -rf "$WATCHDOG_LOCK_DIR"
}

trap cleanup_watchdog EXIT
trap 'exit 0' INT TERM

log_monitor() {
  print -r -- "$(date -u '+%Y-%m-%dT%H:%M:%SZ') watchdog: $*" >> "$MONITOR_LOG"
}

screen_exists() {
  screen -ls | grep -q "[.]${SESSION_NAME}[[:space:]]"
}

pid_matches() {
  local pid="$1"
  local pattern="$2"
  [[ -n "$pid" ]] && ps -p "$pid" -o command= 2>/dev/null | grep -q "$pattern"
}

supervisor_pid() {
  [[ -f "$LOCK_DIR/pid" ]] && cat "$LOCK_DIR/pid" 2>/dev/null || true
}

runner_pid() {
  if [[ -f "$LOCK_DIR/runner.pid" ]]; then
    cat "$LOCK_DIR/runner.pid" 2>/dev/null || true
    return
  fi

  # Supervisors started before runner.pid support still own the runner as a
  # direct child. Keep detection scoped to this worker's supervisor PID.
  local parent_pid="$(supervisor_pid)"
  if pid_matches "$parent_pid" "dxbi_sales_dynamic_supervisor[.]sh"; then
    pgrep -P "$parent_pid" -f "dxbi_sales_dynamic_bucket_runner[.]js" 2>/dev/null | head -n 1
  fi
}

supervisor_alive() {
  local pid="$(supervisor_pid)"
  pid_matches "$pid" "dxbi_sales_dynamic_supervisor[.]sh"
}

scraper_alive() {
  screen_exists || supervisor_alive
}

runner_alive() {
  local pid="$(runner_pid)"
  pid_matches "$pid" "dxbi_sales_dynamic_bucket_runner[.]js"
}

stop_supervisor() {
  local child_pid="$(runner_pid)"
  local parent_pid="$(supervisor_pid)"
  screen -S "$SESSION_NAME" -X quit >/dev/null 2>&1 || true
  if pid_matches "$child_pid" "dxbi_sales_dynamic_bucket_runner[.]js"; then
    kill "$child_pid" >/dev/null 2>&1 || true
  fi
  if pid_matches "$parent_pid" "dxbi_sales_dynamic_supervisor[.]sh"; then
    kill "$parent_pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$LOCK_DIR"
}

latest_summary_reason() {
  node -e "
const fs = require('fs');
const path = require('path');
const dir = process.argv[1];
if (!fs.existsSync(dir)) process.exit(0);
const files = fs.readdirSync(dir)
  .filter((name) => name.endsWith('_summary.json'))
  .map((name) => path.join(dir, name))
  .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
if (!files.length) process.exit(0);
try {
  const parsed = JSON.parse(fs.readFileSync(files[0], 'utf8'));
  const summary = parsed.summary || parsed;
  process.stdout.write(summary.stopped_reason || '');
} catch {}
" "$OUTPUT_DIR"
}

checkpoint_status() {
  node -e "
const fs = require('fs');
const p = process.argv[1];
if (!fs.existsSync(p)) {
  console.log(JSON.stringify({ exists: false }));
  process.exit(0);
}
const state = JSON.parse(fs.readFileSync(p, 'utf8'));
const completed = state.completed_buckets || {};
const failed = state.failed_buckets || {};
const rows = Object.values(completed).reduce((sum, item) => sum + Number(item.rows || 0), 0);
const stat = fs.statSync(p);
console.log(JSON.stringify({
  exists: true,
  completed_buckets: Object.keys(completed).length,
  failed_buckets: Object.keys(failed).length,
  rows,
  mtime_ms: stat.mtimeMs,
  stale_seconds: Math.floor((Date.now() - stat.mtimeMs) / 1000),
}));
" "$STATE_PATH"
}

start_supervisor() {
  /usr/bin/screen -dmS "$SESSION_NAME" /bin/zsh -lc "env DXBI_SALES_CDP_ENDPOINT='${DXBI_SALES_CDP_ENDPOINT:-http://127.0.0.1:9222}' DXBI_SALES_ORDER='${DXBI_SALES_ORDER:-desc}' DXBI_CREDENTIALS_PATH='${DXBI_CREDENTIALS_PATH:-/Users/eier/VV/DXBI-Backfill/dxbi-credentials.json}' DXBI_SALES_START_DATE='${DXBI_SALES_START_DATE:-2007-01-01}' DXBI_SALES_END_DATE='${DXBI_SALES_END_DATE:-2026-07-09}' DXBI_SALES_MAX_REQUESTS='${DXBI_SALES_MAX_REQUESTS:-15000}' DXBI_SALES_DELAY_MIN_MS='${DXBI_SALES_DELAY_MIN_MS:-2500}' DXBI_SALES_DELAY_MAX_MS='${DXBI_SALES_DELAY_MAX_MS:-5500}' DXBI_SALES_RESTART_DELAY_SECONDS='${DXBI_SALES_RESTART_DELAY_SECONDS:-45}' DXBI_SALES_MAX_RESTARTS='${DXBI_SALES_MAX_RESTARTS:-200}' DXBI_SALES_OUTPUT_DIR='$OUTPUT_DIR' DXBI_SALES_STATE_PATH='$STATE_PATH' '$SUPERVISOR'"
}

last_rows=-1
last_row_progress_epoch="$(date +%s)"
last_runner_seen_epoch="$(date +%s)"

log_monitor "starting watchdog session=${SESSION_NAME} interval=${CHECK_INTERVAL_SECONDS}s stall=${STALL_SECONDS}s row_stall=${ROW_STALL_SECONDS}s no_runner=${NO_RUNNER_SECONDS}s"

while true; do
  checkpoint_json="$(checkpoint_status)"
  reason="$(latest_summary_reason)"
  log_monitor "status=${checkpoint_json} latest_reason=${reason:-unknown}"

  if [[ "$reason" == "completed_range" ]]; then
    log_monitor "completed_range detected; watchdog stopping"
    exit 0
  fi

  if ! scraper_alive; then
    log_monitor "scraper supervisor/runner missing; starting supervisor"
    start_supervisor
    sleep "$CHECK_INTERVAL_SECONDS"
    continue
  fi

  rows_now="$(node -e "try { const s = JSON.parse(process.argv[1]); console.log(s.rows || 0); } catch { console.log(0); }" "$checkpoint_json")"
  now_epoch="$(date +%s)"
  if runner_alive; then
    last_runner_seen_epoch="$now_epoch"
  elif [[ $((now_epoch - last_runner_seen_epoch)) -gt "$NO_RUNNER_SECONDS" ]]; then
    log_monitor "node runner missing for $((now_epoch - last_runner_seen_epoch))s; restarting stale supervisor"
    stop_supervisor
    sleep 5
    start_supervisor
    last_runner_seen_epoch="$now_epoch"
  fi

  if [[ "$rows_now" -gt "$last_rows" ]]; then
    last_rows="$rows_now"
    last_row_progress_epoch="$now_epoch"
  fi

  stale_seconds="$(node -e "try { const s = JSON.parse(process.argv[1]); console.log(s.stale_seconds || 0); } catch { console.log(0); }" "$checkpoint_json")"
  if [[ "$stale_seconds" -gt "$STALL_SECONDS" ]]; then
    log_monitor "checkpoint stale for ${stale_seconds}s; restarting scraper screen"
    stop_supervisor
    sleep 10
    start_supervisor
  elif [[ $((now_epoch - last_row_progress_epoch)) -gt "$ROW_STALL_SECONDS" ]]; then
    log_monitor "rows stalled at ${rows_now} for $((now_epoch - last_row_progress_epoch))s; restarting scraper screen"
    stop_supervisor
    sleep 10
    start_supervisor
  fi

  sleep "$CHECK_INTERVAL_SECONDS"
done
