#!/usr/bin/env python3
"""Run a resumable, capped search-page test, not a full-coverage collection."""

from __future__ import annotations

import argparse
import fcntl
import json
import signal
import sqlite3
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

if __package__:
    from . import bayut_collection as collection
else:
    import bayut_collection as collection


class TestStopped(Exception):
    """A configured test limit was reached before the next network call."""


class LimitedFetcher:
    def __init__(
        self,
        fetcher: collection.PageFetcher,
        connection: sqlite3.Connection,
        *,
        max_attempts: int,
        max_response_bytes: int,
        stop_after: int = 0,
        max_consecutive_failures: int = 3,
    ) -> None:
        self.fetcher = fetcher
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(response_bytes), 0), "
            "COALESCE(SUM(outcome <> 'ok'), 0) FROM page_attempts"
        ).fetchone()
        self.attempts, self.response_bytes, self.failures = map(int, row)
        self.max_attempts = max_attempts
        self.stage_limit = self.attempts + stop_after if stop_after else max_attempts
        self.max_response_bytes = max_response_bytes
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failures = 0
        recent = connection.execute(
            "SELECT outcome FROM page_attempts ORDER BY attempt_id DESC LIMIT ?",
            (max_consecutive_failures,),
        ).fetchall()
        for row in recent:
            if row[0] == "ok":
                break
            self.consecutive_failures += 1
        self.last_outcome = recent[0][0] if recent else ""

    def stop_reason(self) -> str:
        if self.last_outcome == "rate_limited":
            return "rate_limited"
        if self.consecutive_failures >= self.max_consecutive_failures:
            return "consecutive_failures"
        if self.attempts >= 10 and self.failures / self.attempts > 0.1:
            return "failure_rate_above_ten_percent"
        if self.response_bytes >= self.max_response_bytes:
            return "measured_response_budget"
        if self.attempts >= self.max_attempts:
            return "attempt_budget"
        if self.attempts >= self.stage_limit:
            return "stage_limit"
        return ""

    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> Any:
        reason = self.stop_reason()
        if reason:
            raise TestStopped(reason)
        result = self.fetcher.fetch(
            search_path=search_path, page_number=page_number, observation_id=observation_id
        )
        self.attempts += 1
        self.response_bytes += int(result.network.get("response_bytes", 0))
        self.last_outcome = result.outcome
        if result.outcome == "ok":
            self.consecutive_failures = 0
        else:
            self.failures += 1
            self.consecutive_failures += 1
        print(
            json.dumps(
                {
                    "event": "page_fetched",
                    "attempt": self.attempts,
                    "path": search_path,
                    "page": page_number,
                    "outcome": result.outcome,
                    "status_code": result.status_code,
                    "cards": len(result.cards),
                    "latency_ms": result.latency_ms,
                    "measured_response_mb": round(self.response_bytes / 1_000_000, 3),
                }
            ),
            flush=True,
        )
        return result

    def invalidate_context(self) -> None:
        self.fetcher.invalidate_context()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=1000)
    parser.add_argument("--max-response-mb", type=int, default=2000)
    parser.add_argument(
        "--stop-after", type=int, default=0, help="Pause after N additional attempts"
    )
    args = parser.parse_args()
    if not 1 <= args.max_attempts <= 1000:
        parser.error("--max-attempts must be between 1 and 1000")
    if not 1 <= args.max_response_mb <= 2000 or args.stop_after < 0:
        parser.error("response budget must be 1..2000 MB; stop-after must be nonnegative")
    config = collection.CollectionConfig.from_json(args.config)
    if config.max_attempts_per_page != 1:
        parser.error("the request test requires max_attempts_per_page=1 (no hidden retries)")
    collection.validate_proxy_environment(config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "request-test.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("another request-test process already owns this output directory")
        _run(args, config)


def _run(args: Any, config: collection.CollectionConfig) -> None:
    connection = collection.open_database(
        config=config, output_dir=args.output_dir, requested_kind="practice"
    )
    initial = collection.collection_status(connection)
    initial.update(
        test_stop_reason="running",
        requested_page_attempts=args.max_attempts,
        attempt_target_reached=initial["page_attempts"] >= args.max_attempts,
        max_measured_response_mb=args.max_response_mb,
    )
    collection._atomic_json(args.output_dir / "test_summary.json", initial)
    print(
        json.dumps(
            {
                "event": "test_started",
                "recorded_attempts": initial["page_attempts"],
                "target_attempts": args.max_attempts,
                "max_measured_response_mb": args.max_response_mb,
            }
        ),
        flush=True,
    )
    reason = "queue_exhausted"
    failed = False

    def stop(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, stop)
    try:
        with (
            sync_playwright() as playwright,
            collection.BrowserPageFetcher(playwright=playwright, config=config) as browser,
        ):
            limited = LimitedFetcher(
                browser,
                connection,
                max_attempts=args.max_attempts,
                max_response_bytes=args.max_response_mb * 1_000_000,
                stop_after=args.stop_after,
                max_consecutive_failures=config.max_consecutive_failed_pages,
            )
            try:
                collection.run_practice(
                    connection=connection, config=config, fetcher=limited, round_robin=True
                )
                reason = limited.stop_reason() or "queue_exhausted"
            except TestStopped as error:
                reason = str(error)
    except KeyboardInterrupt:
        reason = "interrupted"
    except Exception as error:
        # Do not print browser exceptions that could include proxy credentials.
        reason = f"fatal_error:{type(error).__name__}"
        failed = True
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        summary = collection.export_collection(connection, args.output_dir)
        summary.update(
            test_stop_reason=reason,
            requested_page_attempts=args.max_attempts,
            attempt_target_reached=summary["page_attempts"] >= args.max_attempts,
            max_measured_response_mb=args.max_response_mb,
            budget_note="Checked between pages; may overshoot by one page. Not a billed-usage cap.",
        )
        collection._atomic_json(args.output_dir / "test_summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
        connection.close()
    if failed or reason not in {"attempt_budget", "stage_limit"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
