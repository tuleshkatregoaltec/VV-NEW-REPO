"""Refresh local DLD and DXBI data independently, with catch-up after missed runs."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    state = args.data_dir / "DLD-Sync"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "market-sync.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Market data sync is already running", flush=True)
            return 0
        env = dict(os.environ)
        env.update(
            {k: v for k, v in dotenv_values(args.repo_dir / ".env.dev").items() if v is not None}
        )
        env["PYTHONPATH"] = str(args.repo_dir / "holocron")
        env["VITEVUE_REPO_DIR"] = str(args.repo_dir)
        env["DXBI_SYNC_DIR"] = str(args.data_dir / "DXBI-Daily")
        stages = [
            (
                "dld",
                [
                    sys.executable,
                    "-m",
                    "holocron.platform.sync_dld",
                    "--state-dir",
                    str(state),
                    "--geography-pending",
                    str(args.data_dir / "DXBI-Daily/.loaded/geography-pending"),
                ],
            ),
            (
                "dld_projections",
                [
                    sys.executable,
                    "-m",
                    "holocron.platform.sync_silver",
                    "--state-dir",
                    str(state),
                ],
            ),
            (
                "dxbi",
                ["/bin/bash", str(args.repo_dir / "holocron/scripts/sync_dxbi_daily_runs.sh")],
            ),
            (
                "rental_repairs",
                [
                    sys.executable,
                    "-m",
                    "holocron.platform.sync_rental_repairs",
                    "--repo-dir",
                    str(args.repo_dir),
                    "--data-dir",
                    str(args.data_dir),
                ],
            ),
            (
                "import_rentals",
                [
                    str(args.repo_dir / "backend/.venv/bin/python"),
                    "-m",
                    "scripts.crm.refresh_rental_imports",
                    "--state-dir",
                    str(state),
                ],
            ),
        ]
        report: dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "stages": {},
        }
        for name, command in stages:
            if name == "import_rentals" and any(
                report["stages"][stage] != 0 for stage in ("dxbi", "rental_repairs")
            ):
                print(
                    "Imported rental matches deferred: upstream DXBI publication failed", flush=True
                )
                report["stages"][name] = 1
                continue
            print(f"{datetime.now(timezone.utc).isoformat()} Starting {name} sync", flush=True)
            try:
                working_dir = "backend" if name == "import_rentals" else "holocron"
                result = subprocess.run(command, cwd=args.repo_dir / working_dir, env=env)
                report["stages"][name] = result.returncode
            except OSError as exc:
                print(f"{name} could not start: {exc}", flush=True)
                report["stages"][name] = 1
        if all(code == 0 for code in report["stages"].values()):
            cache_code = (
                "import asyncio\n"
                "from app.core.decorators import cache\n"
                "async def clear():\n"
                "    await cache.redis.ping()\n"
                "    for prefix in ('transactions:sales', 'transactions:rentals', 'analytics:'):\n"
                "        await cache.clear_prefix(prefix)\n"
                "    await cache.redis.aclose()\n"
                "asyncio.run(clear())\n"
            )
            result = subprocess.run(
                [str(args.repo_dir / "backend/.venv/bin/python"), "-c", cache_code],
                cwd=args.repo_dir / "backend",
                env=env,
            )
            report["stages"]["cache"] = result.returncode
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["healthy"] = all(code == 0 for code in report["stages"].values())
        temporary = state / "automation-status.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(state / "automation-status.json")
        print(json.dumps(report), flush=True)
        return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
