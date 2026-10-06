#!/usr/bin/env python3
"""Command-line entry point for the standalone Bayut collection bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from bayut_collection import (
    BrowserPageFetcher,
    CollectionConfig,
    collect_shards,
    collection_status,
    export_collection,
    initialize_full_roots,
    initialize_practice_roots,
    open_database,
    plan_collection,
    reset_retryable_errors,
    run_practice,
    sanitized_config,
    validate_proxy_environment,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Standalone Bayut practice and full residential search-card collector."
    )
    parser.add_argument(
        "command",
        choices=("dry-run", "practice", "plan", "collect", "all", "status", "export"),
    )
    parser.add_argument("--config", type=Path, required=True, help="Collection config JSON")
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
        help="Requeue resumable planner, collector, or practice transport failures",
    )
    args = parser.parse_args()
    if args.max_nodes < 0 or args.max_pages < 0:
        parser.error("--max-nodes and --max-pages must be zero or positive")

    config = CollectionConfig.from_json(args.config)
    if config.storage_state_path and not Path(config.storage_state_path).is_file():
        raise FileNotFoundError(f"browser storage state not found: {config.storage_state_path}")
    if args.command == "dry-run":
        payload = sanitized_config(config)
        payload["environment_checked"] = False
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.command not in {"status", "export"}:
        validate_proxy_environment(config)
    elif not (args.output_dir / "collection.sqlite3").is_file():
        parser.error("no existing collection.sqlite3 in --output-dir")

    requested_kind = (
        "practice"
        if args.command == "practice"
        else "full"
        if args.command in {"plan", "collect", "all"}
        else None
    )
    connection = open_database(
        config=config,
        output_dir=args.output_dir,
        requested_kind=requested_kind,
    )
    try:
        if requested_kind == "practice":
            initialize_practice_roots(connection, config)
        elif requested_kind == "full":
            initialize_full_roots(connection, config)
        if args.retry_errors:
            reset_retryable_errors(connection)
        if args.command == "practice":
            with (
                sync_playwright() as playwright,
                BrowserPageFetcher(playwright=playwright, config=config) as fetcher,
            ):
                run_practice(connection=connection, config=config, fetcher=fetcher)
            result = export_collection(connection, args.output_dir)
        elif args.command in {"plan", "all"}:
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
                plan_status.get(status, 0)
                for status in ("plan_pending", "plan_error", "unresolved")
            )
            if args.command == "all" and plan_ready:
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
            result = collection_status(connection)
        elif args.command == "collect":
            with (
                sync_playwright() as playwright,
                BrowserPageFetcher(playwright=playwright, config=config) as fetcher,
            ):
                result = collect_shards(
                    connection=connection,
                    config=config,
                    fetcher=fetcher,
                    max_pages=args.max_pages,
                )
        elif args.command == "export":
            result = export_collection(connection, args.output_dir)
        else:
            result = collection_status(connection)
        if args.command not in {"status", "export", "practice"}:
            result = export_collection(connection, args.output_dir)
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
            for status in (
                "plan_error",
                "collect_error",
                "practice_error",
                "unresolved",
                "count_mismatch",
                "capped",
            )
        ):
            raise SystemExit(2)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
