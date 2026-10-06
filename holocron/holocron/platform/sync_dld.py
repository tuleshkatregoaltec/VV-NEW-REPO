"""Mirror published DLD Open Data rows into the local warehouse over SSH.

The server is read-only. Historical imports remain local; a verified replacement
is published with EXCHANGE TABLES and the previous local table is retained.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import clickhouse_connect

from holocron.platform.settings import settings

logger = logging.getLogger(__name__)
TABLES = tuple(
    f"dld_od_{category}_bronze"
    for category in (
        "transactions",
        "rents",
        "projects",
        "buildings",
        "developers",
        "lands",
        "units",
        "brokers",
        "valuations",
    )
)
SCOPE = "source_system = 'dld_open_data'"

# Executed inside the existing Dagster container. Credentials stay on the server.
REMOTE_WORKER = """
import gzip, json, shutil, sys
import clickhouse_connect
from holocron.platform.settings import settings
request = json.loads(sys.argv[1])
table = request["table"]
allowed = {"dld_od_" + name + "_bronze" for name in (
    "transactions", "rents", "projects", "buildings", "developers", "lands",
    "units", "brokers", "valuations")}
assert table in allowed
c = clickhouse_connect.get_client(
    host=settings.clickhouse_host, port=settings.clickhouse_port,
    username=settings.clickhouse_user, password=settings.clickhouse_password,
    database=settings.clickhouse_database, secure=settings.clickhouse_secure,
    connect_timeout=15, send_receive_timeout=900, query_retries=0)
schema = c.query("SELECT name, type FROM system.columns WHERE database=currentDatabase() "
    "AND table={table:String} AND default_kind != 'ALIAS' ORDER BY position",
    parameters={"table": table}).result_rows
available = dict(schema)
columns = request.get("columns") or [name for name, _ in schema]
assert columns and all(name in available for name in columns)
names = ", ".join("`" + name.replace("`", "``") + "`" for name in columns)
scope = "source_system = 'dld_open_data'"
if request["operation"] == "info":
    stats = c.query(f"SELECT count(), sum(cityHash64(toJSONString(tuple({names})))) "
        f"FROM {table} WHERE {scope} SETTINGS max_threads=2, "
        "output_format_json_quote_64bit_integers=1").result_rows[0]
    print(json.dumps({"schema": schema, "fingerprint": stats}))
elif request["operation"] == "export":
    with c.raw_stream(f"SELECT {names} FROM {table} WHERE {scope} SETTINGS max_threads=2",
                      fmt="Native") as source:
        with gzip.GzipFile(fileobj=sys.stdout.buffer, mode="wb", compresslevel=1) as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
else:
    raise ValueError("Unsupported operation")
"""


def fingerprint(client, table: str, columns: list[str]) -> tuple[int, int]:
    names = ", ".join(f"`{name}`" for name in columns)
    return tuple(
        client.query(
            f"SELECT count(), sum(cityHash64(toJSONString(tuple({names})))) FROM {table} "
            f"WHERE {SCOPE} SETTINGS max_threads=2, output_format_json_quote_64bit_integers=1"
        ).result_rows[0]
    )


def remote_call(remote: str, request: dict, output=None):
    command = shlex.join(
        [
            "docker",
            "exec",
            "holocron-dagster-daemon-1",
            "python",
            "-c",
            REMOTE_WORKER,
            json.dumps(request),
        ]
    )
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
            remote,
            command,
        ],
        stdout=output or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1800,
    )
    if result.returncode:
        raise RuntimeError(
            f"DLD server read failed: {result.stderr.decode(errors='replace')[-1500:]}"
        )
    if output is None:
        return json.loads(result.stdout)
    return None


def sync_table(
    client, *, remote: str, table: str, scratch: Path, pending: Path, dry_run: bool = False
) -> dict:
    schema = client.query(
        "SELECT name, type FROM system.columns WHERE database=currentDatabase() "
        "AND table={table:String} AND default_kind != 'ALIAS' ORDER BY position",
        parameters={"table": table},
    ).result_rows
    if not schema:
        raise RuntimeError(f"Local table is missing: {table}")
    columns = [row[0] for row in schema]
    request = {"table": table, "columns": columns, "operation": "info"}
    source = remote_call(remote, request)
    source_schema = dict(source["schema"])
    if any(source_schema.get(name) != type_name for name, type_name in schema):
        raise RuntimeError(f"Source/local schema mismatch: {table}")
    before = fingerprint(client, table, columns)
    expected = tuple(source["fingerprint"])
    summary: dict[str, Any] = {
        "table": table,
        "before": before,
        "source": expected,
        "changed": before != expected,
    }
    if before == expected or dry_run:
        return summary
    if expected[0] == 0 and before[0] > 0:
        raise RuntimeError(f"Refusing to replace populated {table} with an empty source")

    native = scratch / f"{table}.native.gz"
    logger.info("Downloading %s: %s published rows", table, expected[0])
    with native.open("wb") as output:
        remote_call(remote, {**request, "operation": "export"}, output=output)
    if tuple(remote_call(remote, request)["fingerprint"]) != expected:
        raise RuntimeError(f"Server data changed during export of {table}; retry later")

    staging = f"{table}_local_sync_staging"
    previous = f"{table}_local_sync_previous"
    client.command(f"DROP TABLE IF EXISTS {staging}")
    client.command(f"CREATE TABLE {staging} AS {table}")
    with native.open("rb") as data:
        client.raw_insert(
            staging, column_names=columns, insert_block=data, fmt="Native", compression="gzip"
        )
    downloaded = fingerprint(client, staging, columns)
    if downloaded != expected:
        raise RuntimeError(
            f"Downloaded row count/checksum mismatch for {table}: {downloaded} != {expected}"
        )

    # Preserve separately sourced historical records, including the DLD Pulse import.
    names = ", ".join(f"`{name}`" for name in columns)
    preserved = int(
        client.query(f"SELECT count() FROM {table} WHERE NOT ({SCOPE})").result_rows[0][0]
    )
    client.command(
        f"INSERT INTO {staging} ({names}) SELECT {names} FROM {table} "
        f"WHERE NOT ({SCOPE}) SETTINGS max_threads=2"
    )
    staged_count = int(client.query(f"SELECT count() FROM {staging}").result_rows[0][0])
    if staged_count != preserved + expected[0]:
        raise RuntimeError(f"Historical row preservation check failed for {table}")
    if fingerprint(client, table, columns) != before:
        raise RuntimeError(f"Local data changed during sync of {table}; retry later")
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.touch()
    client.command(f"DROP TABLE IF EXISTS {previous}")
    client.command(f"EXCHANGE TABLES {table} AND {staging}")
    client.command(f"RENAME TABLE {staging} TO {previous}")
    summary.update(preserved_history=preserved, total_rows=staged_count, backup_table=previous)
    logger.info("Published %s; preserved %s historical rows", table, preserved)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="root@188.245.147.179")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--geography-pending", type=Path, required=True)
    parser.add_argument("--tables", nargs="+", choices=TABLES, default=TABLES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state_dir / "sync.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("DLD sync is already running")
            return 0
        client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
            secure=settings.clickhouse_secure,
            connect_timeout=15,
            send_receive_timeout=900,
            query_retries=0,
        )
        report = {"started_at": datetime.now(timezone.utc).isoformat(), "tables": [], "errors": []}
        with tempfile.TemporaryDirectory(dir=args.state_dir, prefix="download-") as temporary:
            for table in args.tables:
                try:
                    summary = sync_table(
                        client,
                        remote=args.remote,
                        table=table,
                        scratch=Path(temporary),
                        pending=args.geography_pending,
                        dry_run=args.dry_run,
                    )
                    report["tables"].append(summary)
                    logger.info("%s", json.dumps(summary))
                except Exception as exc:
                    logger.error("%s: %s", table, exc)
                    report["errors"].append({"table": table, "error": str(exc)})
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        temporary_report = args.state_dir / "latest.json.tmp"
        temporary_report.write_text(json.dumps(report, indent=2) + "\n")
        temporary_report.replace(args.state_dir / "latest.json")
        return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
