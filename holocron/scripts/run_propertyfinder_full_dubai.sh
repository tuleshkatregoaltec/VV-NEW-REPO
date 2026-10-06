#!/usr/bin/env bash
# Runs one fresh full-Dubai plan, then resumes planning and search chunks until
# each durable checkpoint is complete. Any failed Dagster job stops the script.
set -euo pipefail

container_name="${1:-holocron-dagster-webserver-1}"
job_command=(docker exec "$container_name" dagster job execute -m holocron.definitions)

checkpoint_complete() {
  local operation="$1"
  docker exec "$container_name" python -c '
from holocron.platform.resources import ObjectStorageResource
import sys
operation = sys.argv[1]
payload = ObjectStorageResource().client().get_json(
    key=f"state/source=pf_listings/operation={operation}.json"
) or {}
raise SystemExit(0 if payload.get("completed") else 1)
' "$operation"
}

run_job() {
  local job_name="$1"
  local config_path="$2"
  "${job_command[@]}" -j "$job_name" -c "$config_path"
}

run_job pf_listings_plan_snapshot /app/scripts/propertyfinder_full_dubai_plan.yaml
until checkpoint_complete plan_snapshot; do
  run_job pf_listings_plan_snapshot /app/scripts/propertyfinder_full_dubai_plan_resume.yaml
done

until checkpoint_complete search_chunk; do
  run_job pf_listings_search_chunk /app/scripts/propertyfinder_full_dubai_search.yaml
done

echo "Property Finder Dubai current-listing scrape completed."
