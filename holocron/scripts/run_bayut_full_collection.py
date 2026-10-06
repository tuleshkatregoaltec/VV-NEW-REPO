#!/usr/bin/env python3
"""Plan, run, resume, inspect, and export a full Bayut residential collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from holocron.sources.bayut_listings.full_collection import (
    BrowserPageFetcher,
    collect_shards,
    collection_status,
    export_collection,
    initialize_roots,
    load_full_collection_config,
    open_collection_database,
    plan_collection,
    reset_retryable_errors,
    sanitized_full_config,
    validate_full_proxy_environment,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resumable, coverage-aware Bayut Dubai sale/rental card collection."
    )
    parser.add_argument(
        "command",
        choices=("dry-run", "plan", "collect", "all", "status", "export"),
    )
    parser.add_argument("--config", type=Path, required=True, help="Full collection config JSON")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Stable checkpoint/output directory; reuse it to resume",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=0,
        help="Plan at most N hierarchy nodes this invocation; zero is unlimited",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Attempt at most N collection pages (each has bounded retries); zero is unlimited",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Requeue resumable plan/collection errors before running",
    )
    args = parser.parse_args()
    if args.max_nodes < 0 or args.max_pages < 0:
        parser.error("--max-nodes and --max-pages must be zero or positive")

    config = load_full_collection_config(args.config)
    if config.storage_state_path and not Path(config.storage_state_path).is_file():
        raise FileNotFoundError(f"Bayut storage state not found: {config.storage_state_path}")
    if args.command == "dry-run":
        payload = sanitized_full_config(config)
        payload["environment_checked"] = False
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.command not in {"status", "export"}:
        validate_full_proxy_environment(config)
    elif not (args.output_dir / "collection.sqlite3").is_file():
        parser.error("no existing collection.sqlite3 in --output-dir")

    connection = open_collection_database(config=config, output_dir=args.output_dir)
    try:
        if args.command not in {"status", "export"}:
            initialize_roots(connection, config)
        if args.retry_errors:
            reset_retryable_errors(connection)
        if args.command in {"plan", "all"}:
            with (
                sync_playwright() as playwright,
                BrowserPageFetcher(playwright=playwright, config=config) as fetcher,
            ):
                plan_collection(
                    connection=connection,
                    config=config,
                    fetcher=fetcher,
                    max_nodes=args.max_nodes,
                )
        plan_status = collection_status(connection)["shard_statuses"]
        plan_ready = not any(
            plan_status.get(status, 0) for status in ("plan_pending", "plan_error", "unresolved")
        )
        if args.command == "collect" or (args.command == "all" and plan_ready):
            with (
                sync_playwright() as playwright,
                BrowserPageFetcher(playwright=playwright, config=config) as fetcher,
            ):
                collect_shards(
                    connection=connection,
                    config=config,
                    fetcher=fetcher,
                    max_pages=args.max_pages,
                )
        result = (
            collection_status(connection)
            if args.command == "status"
            else export_collection(connection, args.output_dir)
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        if (
            args.command in {"collect", "all"}
            and result["remaining_collectable_shards"] == 0
            and not result["shard_statuses"].get("plan_pending", 0)
            and result["coverage_status"] != "complete"
        ):
            raise SystemExit(2)
        if args.command not in {"status", "export"} and any(
            result["shard_statuses"].get(status, 0)
            for status in ("plan_error", "collect_error", "unresolved", "count_mismatch", "capped")
        ):
            raise SystemExit(2)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
