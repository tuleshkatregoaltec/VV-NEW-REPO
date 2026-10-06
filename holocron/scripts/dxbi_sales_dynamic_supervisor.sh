#!/bin/zsh
set -u

RUNNER="${DXBI_SALES_RUNNER:-/Users/eier/VV/vitevue-platform-full-platform/holocron/scripts/dxbi_sales_dynamic_bucket_runner.js}"
OUTPUT_DIR="${DXBI_SALES_OUTPUT_DIR:-/Users/eier/VV/DXBI-Backfill/sales-dynamic-full}"
BACKFILL_LOG="${DXBI_SALES_BACKFILL_LOG:-$OUTPUT_DIR/backfill.log}"
SUPERVISOR_LOG="${DXBI_SALES_SUPERVISOR_LOG:-$OUTPUT_DIR/supervisor.log}"
RESTART_DELAY_SECONDS="${DXBI_SALES_RESTART_DELAY_SECONDS:-45}"
MAX_RESTARTS="${DXBI_SALES_MAX_RESTARTS:-200}"
LOCK_DIR="${DXBI_SALES_SUPERVISOR_LOCK_DIR:-$OUTPUT_DIR/supervisor.lock}"

mkdir -p "$OUTPUT_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  print -r -- "$(date -u '+%Y-%m-%dT%H:%M:%SZ') supervisor: another supervisor is already active; exiting" >> "$SUPERVISOR_LOG"
  exit 0
fi

print -r -- "$$" > "$LOCK_DIR/pid"

runner_pid=""

cleanup() {
  if [[ -n "${runner_pid:-}" ]] && kill -0 "$runner_pid" >/dev/null 2>&1; then
    kill "$runner_pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$LOCK_DIR"
}

trap cleanup EXIT
trap 'exit 0' INT TERM

restart_count=0

log_supervisor() {
  print -r -- "$(date -u '+%Y-%m-%dT%H:%M:%SZ') supervisor: $*" >> "$SUPERVISOR_LOG"
}

latest_reason() {
  node -e "
const fs = require('fs');
const path = require('path');
const dir = process.argv[1];
const files = fs.readdirSync(dir)
  .filter((name) => name.endsWith('_summary.json'))
  .map((name) => path.join(dir, name))
  .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
if (!files.length) process.exit(0);
try {
  const summary = JSON.parse(fs.readFileSync(files[0], 'utf8')).summary || JSON.parse(fs.readFileSync(files[0], 'utf8'));
  process.stdout.write(summary.stopped_reason || '');
} catch {}
" "$OUTPUT_DIR"
}

log_supervisor "starting supervised DXBI sales scrape"

while true; do
  log_supervisor "launching runner restart_count=$restart_count"
  node "$RUNNER" >> "$BACKFILL_LOG" 2>&1 &
  runner_pid=$!
  print -r -- "$runner_pid" > "$LOCK_DIR/runner.pid"
  wait "$runner_pid"
  exit_code=$?
  rm -f "$LOCK_DIR/runner.pid"
  runner_pid=""
  reason="$(latest_reason)"

  if [[ "$exit_code" -eq 0 ]]; then
    log_supervisor "runner exited cleanly reason=${reason:-unknown}; supervisor stopping"
    exit 0
  fi

  restart_count=$((restart_count + 1))
  log_supervisor "runner failed exit_code=$exit_code reason=${reason:-unknown}; restarting after ${RESTART_DELAY_SECONDS}s"

  if [[ "$restart_count" -ge "$MAX_RESTARTS" ]]; then
    log_supervisor "max restarts reached ($MAX_RESTARTS); supervisor stopping"
    exit "$exit_code"
  fi

  sleep "$RESTART_DELAY_SECONDS"
done
