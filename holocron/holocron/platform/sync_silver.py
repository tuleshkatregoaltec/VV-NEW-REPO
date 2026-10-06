"""Catch up local DLD projections after bronze sync, retaining the previous tables."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from holocron.platform.clickhouse import ClickHouseClient
from holocron.platform.settings import settings
from holocron.silver.transforms import _SILVER_RENT_CONTRACTS_SQL, _SILVER_TRANSACTIONS_SQL

PROJECTIONS = (
    (
        "silver_transactions",
        "dld_od_transactions_bronze",
        "transaction_date",
        _SILVER_TRANSACTIONS_SQL,
    ),
    (
        "silver_rent_contracts",
        "dld_od_rents_bronze",
        "registration_date",
        _SILVER_RENT_CONTRACTS_SQL,
    ),
)
LIMITS = " SETTINGS max_threads=2, max_memory_usage=3000000000"


def source_fingerprint(client, table: str) -> list[int]:
    columns = client.query(
        "SELECT name FROM system.columns WHERE database=currentDatabase() "
        "AND table={table:String} AND default_kind != 'ALIAS' ORDER BY position",
        parameters={"table": table},
    ).result_rows
    if not columns:
        raise RuntimeError(f"Missing source table: {table}")
    names = ", ".join(f"`{row[0]}`" for row in columns)
    return list(
        client.query(
            f"SELECT count(), sum(cityHash64(toJSONString(tuple({names})))) FROM `{table}`" + LIMITS
        ).result_rows[0]
    )


def table_summary(client, table: str, date_column: str) -> dict:
    count, first, last = client.query(
        f"SELECT count(), minOrNull(`{date_column}`), maxOrNull(`{date_column}`) "
        f"FROM `{table}` FINAL" + LIMITS
    ).result_rows[0]
    return {
        "count": count,
        "first_date": str(first) if first else None,
        "last_date": str(last) if last else None,
    }


def validate_replacement(before: dict, after: dict) -> None:
    if not before["count"]:
        return
    if not after["count"]:
        raise RuntimeError("Refusing to replace a populated projection with an empty table")
    if after["first_date"] > before["first_date"] or after["last_date"] < before["last_date"]:
        raise RuntimeError("Projection date coverage regressed; retaining the current table")


def refresh_projection(
    client, *, table: str, source: str, date_column: str, sql: str, state_dir: Path
) -> dict:
    marker = state_dir / f"{table}.json"
    previous = json.loads(marker.read_text()) if marker.exists() else {}
    fingerprint = source_fingerprint(client, source)
    transform_hash = hashlib.sha256(sql.encode()).hexdigest()
    before = table_summary(client, table, date_column)
    if (
        previous.get("source_fingerprint") == fingerprint
        and previous.get("transform_hash") == transform_hash
        and previous.get("published") == before
    ):
        return {"table": table, "changed": False, "published": before}

    staging = f"{table}_local_sync_staging"
    backup = f"{table}_local_sync_previous"
    client.command(f"DROP TABLE IF EXISTS `{staging}`")
    client.command(f"CREATE TABLE `{staging}` AS `{table}`")
    exchanged = False
    try:
        insert_sql = sql.replace(f"INSERT INTO `{table}_staging`", f"INSERT INTO `{staging}`", 1)
        if insert_sql == sql:
            raise RuntimeError(f"Unexpected projection INSERT target: {table}")
        client.command(insert_sql + LIMITS)
        after = table_summary(client, staging, date_column)
        validate_replacement(before, after)
        if fingerprint != source_fingerprint(client, source):
            raise RuntimeError(f"Source changed during projection rebuild: {source}")
        client.command(f"DROP TABLE IF EXISTS `{backup}`")
        client.command(f"EXCHANGE TABLES `{table}` AND `{staging}`")
        exchanged = True
        client.command(f"RENAME TABLE `{staging}` TO `{backup}`")
    finally:
        # After exchange, staging contains the old table. Keep it if rename failed.
        if not exchanged:
            client.command(f"DROP TABLE IF EXISTS `{staging}`")

    report = {
        "table": table,
        "changed": True,
        "source_fingerprint": fingerprint,
        "transform_hash": transform_hash,
        "before": before,
        "published": after,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = marker.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(marker)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state_dir / "silver-sync.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("DLD projection refresh is already running", flush=True)
            return 1
        client = ClickHouseClient(settings)._client
        failed = False
        try:
            for table, source, date_column, sql in PROJECTIONS:
                try:
                    print(
                        json.dumps(
                            refresh_projection(
                                client,
                                table=table,
                                source=source,
                                date_column=date_column,
                                sql=sql,
                                state_dir=args.state_dir,
                            )
                        ),
                        flush=True,
                    )
                except Exception as exc:
                    failed = True
                    print(json.dumps({"table": table, "error": str(exc)}), flush=True)
        finally:
            client.close()
        return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
