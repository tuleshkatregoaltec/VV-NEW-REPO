#!/usr/bin/env python3
"""Run a bounded Bayut CAPTCHA attribution experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from holocron.sources.bayut_listings.probe import (
    build_trial_schedule,
    load_probe_plan,
    run_probe,
    sanitized_plan,
    validate_proxy_environment,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run randomized, bounded Bayut challenge-attribution cohorts."
    )
    parser.add_argument("--plan", type=Path, required=True, help="Probe plan JSON file")
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Parent directory for a new timestamped evidence directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the sanitized plan without launching a browser",
    )
    args = parser.parse_args()

    plan = load_probe_plan(args.plan)
    validate_proxy_environment(plan)
    if args.dry_run:
        payload = sanitized_plan(plan)
        payload["trial_schedule"] = [
            {
                "cohort": task.cohort.name,
                "trial": task.trial,
                "search_path": task.search_path,
            }
            for task in build_trial_schedule(plan)
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    run_dir = run_probe(plan=plan, output_root=args.output_root)
    print(json.dumps({"run_dir": str(run_dir), "summary": str(run_dir / "summary.json")}, indent=2))


if __name__ == "__main__":
    main()
