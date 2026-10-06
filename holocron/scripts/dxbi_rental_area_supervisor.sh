#!/usr/bin/env bash
set -u

if [[ $# -ne 7 ]]; then
  echo "usage: $0 CREDENTIALS STORAGE_STATE LOCATIONS_TSV OUTPUT_DIR START_DATE END_DATE DIRECTION" >&2
  exit 2
fi

credentials=$1
storage_state=$2
locations_tsv=$3
output_dir=$4
start_date=$5
end_date=$6
direction=$7
runner=/root/repos/vitevue-platform/holocron/scripts/dxbi_rental_gap_backfill.py
python=/root/repos/vitevue-platform/holocron/.venv/bin/python
browser=/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome
status=0

while IFS=$'\t' read -r location_id location_text location_slug; do
  [[ -n "$location_id" ]] || continue
  echo "START location_id=$location_id location=$location_text"
  if ! "$python" "$runner" \
    --credentials "$credentials" \
    --storage-state "$storage_state" \
    --browser "$browser" \
    --output-dir "$output_dir/locations/$location_id" \
    --start-date "$start_date" \
    --end-date "$end_date" \
    --direction "$direction" \
    --template-date 2025-07-01 \
    --delay-min 1 \
    --delay-max 2 \
    --location-id "$location_id" \
    --location-text "$location_text" \
    --location-slug "$location_slug"; then
    echo "FAILED location_id=$location_id location=$location_text" >&2
    status=1
  fi
done < "$locations_tsv"

exit "$status"
