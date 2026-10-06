"""Run one resumable, isolated rental repair date without overlapping daily collection."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def accepted_run(report: dict, minimum_rows: int) -> bool:
    return (
        report.get("status") == "success"
        and report.get("expected_partitions") == 1
        and report.get("completed_partitions") == 1
        and report.get("failed_partitions", 0) == 0
        and report.get("missing_partitions", 0) == 0
        and report.get("raw_rows", 0) >= max(1, minimum_rows)
    )


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--scraper", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--storage-state", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path("/run/lock/vitevue-dxbi-rentals.lock"))
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    # Leave a quiet window around the existing 00:30 UTC daily rental timer.
    if now.hour < 3 or now.hour >= 23:
        print("Repair queue paused for overnight collection", flush=True)
        return 0
    args.state_dir.mkdir(parents=True, exist_ok=True)
    args.lock.parent.mkdir(parents=True, exist_ok=True)
    with args.lock.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Daily rental collection is running; repair will retry later", flush=True)
            return 0
        plan = json.loads(args.plan.read_text())
        scraper_version = hashlib.sha256(args.scraper.read_bytes()).hexdigest()
        state_path = args.state_dir / "queue-status.json"
        state: dict[str, Any] = (
            json.loads(state_path.read_text()) if state_path.exists() else {"dates": {}}
        )
        selected = None
        for item in plan["dates"]:
            saved = state["dates"].get(item["date"], {})
            if saved.get("status") == "complete":
                continue
            retry_at = saved.get("retry_at")
            if (
                retry_at
                and saved.get("scraper_sha256") == scraper_version
                and datetime.fromisoformat(retry_at) > now
            ):
                continue
            selected = item
            break
        if selected is None:
            print("No repair dates due", flush=True)
            return 0
        day = selected["date"]
        prior = state["dates"].get(day, {})
        attempt = int(prior.get("attempts", 0)) + 1
        # Each attempt gets a fresh authenticated collection. A false empty run
        # cannot poison subsequent retries through old completed checkpoints.
        output = args.state_dir / "runs" / f"date={day}-attempt={attempt:03d}"
        output.mkdir(parents=True, exist_ok=True)
        record = {
            "status": "running",
            "attempts": attempt,
            "started_at": now.isoformat(),
            "reason": selected["reason"],
            "output": str(output),
            "scraper_sha256": scraper_version,
        }
        state["dates"][day] = record
        write_json(state_path, state)
        command = [
            sys.executable,
            str(args.scraper),
            "--credentials",
            str(args.credentials),
            "--storage-state",
            str(args.storage_state),
            "--browser",
            str(args.browser),
            "--output-dir",
            str(output),
            "--start-date",
            day,
            "--end-date",
            day,
            "--direction",
            "asc",
            "--template-date",
            "2025-01-01",
            "--delay-min",
            "2",
            "--delay-max",
            "4",
            "--max-requests",
            "2000",
            "--report",
            "rentals",
            "--account-id",
            "account-b",
            "--run-id",
            f"rental-repair-{day}-{attempt}",
            "--manifest-path",
            str(args.manifest),
            "--collection-strategy",
            "split",
            "--profile-ids",
            "broad",
            "--location-ids",
            "1",
        ]
        print(f"Repairing {day}: {selected['reason']}; attempt {attempt}", flush=True)
        try:
            with (output / "scrape.log").open("w") as log:
                result = subprocess.run(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=2400,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
            report_path = output / "reconciliation.json"
            report = json.loads(report_path.read_text()) if report_path.exists() else {}
            valid = result.returncode == 0 and accepted_run(report, selected["minimum_rows"])
            record.update(returncode=result.returncode, raw_rows=report.get("raw_rows", 0))
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            valid = False
            record["error"] = str(exc)
        finished = datetime.now(timezone.utc)
        record["finished_at"] = finished.isoformat()
        record["status"] = "complete" if valid else "retry"
        if valid:
            (output / "_VERIFIED").touch()
        else:
            # Keep incomplete raw data for diagnosis, but never publish it.
            (output / "_SUCCESS").unlink(missing_ok=True)
            record["retry_at"] = (finished + timedelta(hours=24)).isoformat()
            record.setdefault("error", "Incomplete scrape or below the historical density floor")
        state["updated_at"] = finished.isoformat()
        state["completed_dates"] = sum(r["status"] == "complete" for r in state["dates"].values())
        state["planned_dates"] = len(plan["dates"])
        write_json(state_path, state)
        print(json.dumps({"date": day, **record}), flush=True)
        return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
