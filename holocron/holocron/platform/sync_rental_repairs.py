"""Import only verified historical repair runs into the active local rental v2 tables."""

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from holocron.platform.clickhouse import ClickHouseClient
from holocron.platform.settings import settings


def verified_run(path: Path) -> bool:
    if not (path / "_VERIFIED").is_file() or not (path / "_SUCCESS").is_file():
        return False
    report = json.loads((path / "reconciliation.json").read_text())
    return (
        report.get("status") == "success"
        and report.get("expected_partitions") == report.get("completed_partitions") == 1
        and report.get("failed_partitions", 0) == 0
        and report.get("missing_partitions", 0) == 0
        and report.get("raw_rows", 0) > 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    local = args.data_dir / "DXBI-Repair"
    runs = local / "runs"
    loaded = local / ".loaded"
    runs.mkdir(parents=True, exist_ok=True)
    loaded.mkdir(exist_ok=True)
    with (local / "sync.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        subprocess.run(
            [
                "rsync",
                "-az",
                "--partial",
                "-e",
                "ssh -o BatchMode=yes -o ConnectTimeout=15",
                "root@188.245.147.179:/root/data/dxbi-rental-repair-20260915/runs/",
                str(runs) + "/",
            ],
            check=True,
            timeout=900,
        )
        pending = [
            p
            for p in sorted(runs.iterdir())
            if p.is_dir() and not (loaded / p.name).exists() and verified_run(p)
        ]
        if not pending:
            print("No new verified rental repairs", flush=True)
            return 0
        c = ClickHouseClient(settings)._client
        active_v2 = c.query(
            "SELECT count() FROM system.columns WHERE database=currentDatabase() "
            "AND table='dxbi_rental_events' AND name='contract_key'"
        ).result_rows[0][0]
        if not active_v2:
            print("Verified repairs downloaded; awaiting the local v2 publication", flush=True)
            return 0
        run_id = "rental-repairs-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        scripts = args.repo_dir / "holocron/scripts"
        subprocess.run(
            [
                sys.executable,
                str(scripts / "load_dxbi_rental_events.py"),
                "--target",
                "active",
                "--run-id",
                run_id,
                "--reconciliation-output",
                str(local / (run_id + ".json")),
                *map(str, pending),
            ],
            check=True,
        )
        geography_pending = args.data_dir / "DXBI-Daily/.loaded/geography-pending"
        geography_pending.touch()
        subprocess.run(
            [sys.executable, str(scripts / "load_dxbi_sales_units.py"), "--refresh-matches-only"],
            check=True,
        )
        subprocess.run(
            [sys.executable, str(scripts / "refresh_geography_crosswalk.py")], check=True
        )
        geography_pending.unlink(missing_ok=True)
        for run in pending:
            (loaded / run.name).touch()
        print(f"Published {len(pending)} verified rental repair runs", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
