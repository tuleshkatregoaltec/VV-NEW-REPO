#!/usr/bin/env python3
"""Normalize retained DXB rental shards and load the shadow v2 ClickHouse tables."""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import clickhouse_connect

from holocron.sources.dxbi.rental_events import (
    legacy_rental_event,
    merge_rental_snapshots,
    normalize_rental_rows,
    source_account_from_path,
)

logger = logging.getLogger("dxbi_rental_loader")

TABLE = "dxbi_rental_events_v2"
INDEX_TABLE = "dxbi_rental_unit_candidates_v2"
RECONCILIATION_TABLE = "dxbi_rental_run_reconciliation"
LEGACY_TARGET = False
_DATE_PATH = re.compile(r"(?:^|/)(?:date[=/])(?P<date>\d{4}-\d{2}-\d{2})(?:/|$)")

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    contract_key String,
    event_key String ALIAS contract_key,
    source_contract_id String DEFAULT '',
    unit_number String DEFAULT '',
    occurrence_index UInt16 DEFAULT 1,
    source_cohort_size UInt32 DEFAULT 0,
    unit_candidate_key String,
    unit_cohort_key String,
    location_name String DEFAULT '',
    building_name String DEFAULT '',
    project_name String DEFAULT '',
    area_name LowCardinality(String) DEFAULT '',
    property_type LowCardinality(String) DEFAULT '',
    bedrooms LowCardinality(String) DEFAULT '',
    size_sqft Float64 DEFAULT 0,
    contract_amount_aed UInt64 DEFAULT 0,
    contract_term_days UInt32 DEFAULT 0,
    contract_term_months Float32 DEFAULT 0,
    annual_rent_aed UInt64 DEFAULT 0,
    rent_normalization_version UInt8 DEFAULT 2,
    address_normalization_version UInt8 DEFAULT 5,
    purchase_price_aed UInt64 DEFAULT 0,
    lease_start Date,
    lease_end Date,
    contract_state LowCardinality(String) DEFAULT '',
    source_account LowCardinality(String),
    source_run_id String,
    report_type LowCardinality(String) DEFAULT 'rentals',
    filter_profile_id LowCardinality(String),
    source_location_id String,
    source_location_text String DEFAULT '',
    source_location_slug String DEFAULT '',
    configuration_hash FixedString(20),
    raw_row_fingerprint FixedString(64),
    raw_attributes_json String DEFAULT '{{}}',
    source_shard_date Date,
    source_file String DEFAULT '',
    scraped_at DateTime64(3, 'UTC'),
    loaded_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (lease_start, contract_key)
"""

COLUMNS = [
    "contract_key",
    "source_contract_id",
    "unit_number",
    "occurrence_index",
    "source_cohort_size",
    "unit_candidate_key",
    "unit_cohort_key",
    "location_name",
    "building_name",
    "project_name",
    "area_name",
    "property_type",
    "bedrooms",
    "size_sqft",
    "contract_amount_aed",
    "contract_term_days",
    "contract_term_months",
    "annual_rent_aed",
    "rent_normalization_version",
    "address_normalization_version",
    "purchase_price_aed",
    "lease_start",
    "lease_end",
    "contract_state",
    "source_account",
    "source_run_id",
    "report_type",
    "filter_profile_id",
    "source_location_id",
    "source_location_text",
    "source_location_slug",
    "configuration_hash",
    "raw_row_fingerprint",
    "raw_attributes_json",
    "source_shard_date",
    "source_file",
    "scraped_at",
]

CREATE_INDEX_SQL = f"""
CREATE TABLE IF NOT EXISTS {INDEX_TABLE} (
    contract_key String,
    event_key String ALIAS contract_key,
    unit_candidate_key String,
    unit_cohort_key String,
    source_contract_id String DEFAULT '',
    unit_number String DEFAULT '',
    location_name String DEFAULT '',
    building_name String DEFAULT '',
    project_name String DEFAULT '',
    area_name LowCardinality(String) DEFAULT '',
    property_type LowCardinality(String) DEFAULT '',
    bedrooms LowCardinality(String) DEFAULT '',
    size_sqft Float64 DEFAULT 0,
    contract_amount_aed UInt64 DEFAULT 0,
    contract_term_days UInt32 DEFAULT 0,
    contract_term_months Float32 DEFAULT 0,
    annual_rent_aed UInt64 DEFAULT 0,
    rent_normalization_version UInt8 DEFAULT 2,
    address_normalization_version UInt8 DEFAULT 5,
    purchase_price_aed UInt64 DEFAULT 0,
    lease_start Date,
    lease_end Date,
    contract_state LowCardinality(String) DEFAULT '',
    observed_contracts UInt32 DEFAULT 0,
    last_scraped_at DateTime64(3, 'UTC'),
    loaded_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (contract_key, unit_candidate_key)
"""

REFRESH_INDEX_SQL = f"""
INSERT INTO {INDEX_TABLE} (
    contract_key,
    unit_candidate_key,
    unit_cohort_key,
    source_contract_id,
    unit_number,
    location_name,
    building_name,
    project_name,
    area_name,
    property_type,
    bedrooms,
    size_sqft,
    contract_amount_aed,
    contract_term_days,
    contract_term_months,
    annual_rent_aed,
    rent_normalization_version,
    address_normalization_version,
    purchase_price_aed,
    lease_start,
    lease_end,
    contract_state,
    observed_contracts,
    last_scraped_at,
    loaded_at
)
SELECT
    argMax(contract_key, tuple(lease_start, lease_end, scraped_at, contract_key)),
    unit_candidate_key,
    argMax(unit_cohort_key, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(source_contract_id, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(unit_number, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(location_name, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(building_name, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(project_name, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(area_name, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(property_type, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(bedrooms, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(size_sqft, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(contract_amount_aed, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(contract_term_days, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(contract_term_months, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(annual_rent_aed, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(rent_normalization_version, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(address_normalization_version, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(purchase_price_aed, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(lease_start, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(lease_end, tuple(lease_start, lease_end, scraped_at, contract_key)),
    argMax(contract_state, tuple(lease_start, lease_end, scraped_at, contract_key)),
    toUInt32(count()),
    max(scraped_at),
    now64(3)
FROM {TABLE} FINAL
WHERE lease_start >= toDate('2025-01-01')
GROUP BY unit_candidate_key
"""

CREATE_RECONCILIATION_SQL = f"""
CREATE TABLE IF NOT EXISTS {RECONCILIATION_TABLE} (
    run_id String,
    report_type LowCardinality(String),
    status LowCardinality(String),
    raw_rows UInt64,
    unique_source_rows UInt64,
    normalized_rows UInt64,
    quarantined_rows UInt64,
    profile_overlap_rows UInt64,
    loaded_contracts UInt64,
    out_of_scope_rows UInt64,
    expected_partitions UInt32,
    completed_partitions UInt32,
    failed_partitions UInt32,
    manifest_hash String DEFAULT '',
    details_json String DEFAULT '{{}}',
    started_at DateTime64(3, 'UTC'),
    finished_at DateTime64(3, 'UTC'),
    loaded_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (report_type, run_id)
"""


def discover_files(inputs: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in inputs:
        if path.is_file() and path.name.endswith((".jsonl", ".jsonl.gz")):
            files.add(path)
        elif path.is_dir():
            shard_root = path / "shards"
            search_root = shard_root if shard_root.is_dir() else path
            files.update(search_root.rglob("*.jsonl"))
            files.update(search_root.rglob("*.jsonl.gz"))
        else:
            raise FileNotFoundError(f"Input does not exist: {path}")
    return sorted(files)


def _open(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def _source_day(path: Path) -> str:
    match = _DATE_PATH.search(path.as_posix())
    if match:
        return match.group("date")
    try:
        with _open(path) as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                shard = payload.get("shard") if isinstance(payload.get("shard"), dict) else {}
                value = str(shard.get("date") or payload.get("shard_start_date") or "")
                return date.fromisoformat(value).isoformat()
    except (EOFError, OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        pass
    return "unknown"


def group_files_by_day(files: list[Path]) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        grouped[_source_day(path)].append(path)
    return dict(sorted(grouped.items()))


def _read_payloads(
    files: list[Path],
) -> tuple[list[tuple[dict[str, Any], str, str]], list[dict[str, Any]], int]:
    payloads: list[tuple[dict[str, Any], str, str]] = []
    quarantined: list[dict[str, Any]] = []
    raw_lines = 0
    for path in files:
        try:
            with _open(path) as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                        if not isinstance(payload, dict):
                            raise TypeError("row is not a JSON object")
                    except (TypeError, json.JSONDecodeError) as exc:
                        raw_lines += 1
                        quarantined.append(
                            {
                                "reason": f"{type(exc).__name__}: {exc}",
                                "source_file": str(path),
                                "line_number": line_number,
                                "raw_line": line.rstrip("\n"),
                            }
                        )
                        continue
                    report_type = str(
                        payload.get("report_type") or payload.get("transaction_type") or "rentals"
                    ).lower()
                    if report_type not in {"rent", "rental", "rentals"}:
                        continue
                    raw_lines += 1
                    payloads.append((payload, str(path), source_account_from_path(path)))
        except (EOFError, OSError, UnicodeDecodeError) as exc:
            raw_lines += 1
            quarantined.append(
                {
                    "reason": f"{type(exc).__name__}: {exc}",
                    "source_file": str(path),
                }
            )
    return payloads, quarantined, raw_lines


def load_files(
    files: list[Path],
    *,
    client,
    min_start_date: date,
    batch_size: int,
    quarantine_path: Path | None = None,
) -> dict[str, int]:
    merge_active = TABLE == "dxbi_rental_events" and not LEGACY_TARGET
    target = TABLE + "_history_refresh" if merge_active else TABLE
    grouped = group_files_by_day(files)
    if merge_active:
        if "unknown" in grouped:
            raise RuntimeError("Active rental updates require known source dates")
        client.command(f"DROP TABLE IF EXISTS {target}")
        client.command(f"CREATE TABLE {target} AS {TABLE}")
    totals = {
        "raw_rows": 0,
        "unique_source_rows": 0,
        "normalized_rows": 0,
        "quarantined_rows": 0,
        "profile_overlap_rows": 0,
        "loaded_contracts": 0,
        "out_of_scope_rows": 0,
    }
    quarantined_rows: list[dict[str, Any]] = []
    for day, day_files in grouped.items():
        payloads, malformed, raw_lines = _read_payloads(day_files)
        result = normalize_rental_rows(payloads)
        day_quarantine = [*malformed, *result.quarantined]
        events = [event for event in result.events if event["lease_start"] >= min_start_date]
        out_of_scope = len(result.events) - len(events)
        if LEGACY_TARGET:
            events = [legacy_rental_event(event) for event in events]
        elif merge_active:
            if any(event["lease_start"].isoformat() != day for event in events):
                raise RuntimeError("Rental source date differs from lease-start date")
            existing = list(
                client.query(
                    f"SELECT {', '.join(COLUMNS)} FROM {TABLE} FINAL WHERE lease_start={{day:Date}}",
                    parameters={"day": day},
                ).named_results()
            )
            # ClickHouse returns FixedString values as bytes. Mixed historical
            # and newly normalized batches must use one representation.
            for event in existing:
                for column in ("configuration_hash", "raw_row_fingerprint"):
                    if isinstance(event[column], bytes):
                        event[column] = event[column].decode("utf-8").rstrip("\x00")
            events = merge_rental_snapshots([*existing, *events])
        totals["raw_rows"] += raw_lines
        totals["unique_source_rows"] += result.unique_source_rows
        totals["normalized_rows"] += result.normalized_rows
        totals["quarantined_rows"] += len(day_quarantine)
        totals["profile_overlap_rows"] += result.profile_overlap
        totals["out_of_scope_rows"] += out_of_scope
        quarantined_rows.extend(day_quarantine)

        for offset in range(0, len(events), batch_size):
            batch_events = events[offset : offset + batch_size]
            client.insert(
                target,
                [[event[column] for column in COLUMNS] for event in batch_events],
                column_names=COLUMNS,
            )
            totals["loaded_contracts"] += len(batch_events)
        logger.info(
            "date=%s raw=%s normalized=%s quarantined=%s overlap=%s loaded=%s",
            day,
            raw_lines,
            result.normalized_rows,
            len(day_quarantine),
            result.profile_overlap,
            len(events),
        )

    if totals["raw_rows"] != totals["normalized_rows"] + totals["quarantined_rows"]:
        raise RuntimeError(
            "rental reconciliation invariant failed: "
            "raw_rows must equal normalized_rows + quarantined_rows"
        )
    if quarantine_path and quarantined_rows:
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        with quarantine_path.open("w", encoding="utf-8") as handle:
            for row in quarantined_rows:
                handle.write(
                    json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":"))
                )
                handle.write("\n")
    elif quarantine_path:
        quarantine_path.unlink(missing_ok=True)
    if merge_active:
        if totals["quarantined_rows"]:
            raise RuntimeError("Active rental update contains invalid rows; previous data retained")
        client.command(
            f"INSERT INTO {target} SELECT * FROM {TABLE} FINAL "
            "WHERE lease_start NOT IN {days:Array(Date)} SETTINGS max_threads=2",
            parameters={"days": [date.fromisoformat(day) for day in grouped]},
        )
        client.command(f"EXCHANGE TABLES {TABLE} AND {target}")
        client.command(f"DROP TABLE {target}")
    return totals


def configure_target(client, target: str) -> None:
    global TABLE, INDEX_TABLE, CREATE_TABLE_SQL, CREATE_INDEX_SQL, REFRESH_INDEX_SQL
    global COLUMNS, LEGACY_TARGET

    use_active = target == "active"
    if target == "auto":
        result = client.query(
            """
            SELECT count()
            FROM system.columns
            WHERE database = currentDatabase()
              AND table = 'dxbi_rental_events'
              AND name = 'contract_key'
            """
        )
        use_active = bool(result.result_rows[0][0])
    if not use_active:
        return

    old_table = TABLE
    old_index = INDEX_TABLE
    TABLE = "dxbi_rental_events"
    INDEX_TABLE = "dxbi_rental_unit_candidates"
    CREATE_TABLE_SQL = CREATE_TABLE_SQL.replace(old_table, TABLE)
    CREATE_INDEX_SQL = CREATE_INDEX_SQL.replace(old_index, INDEX_TABLE)
    REFRESH_INDEX_SQL = REFRESH_INDEX_SQL.replace(old_index, INDEX_TABLE).replace(old_table, TABLE)
    active_columns = [
        row[0]
        for row in client.query(
            "SELECT name FROM system.columns WHERE database = currentDatabase() "
            "AND table = 'dxbi_rental_events' ORDER BY position"
        ).result_rows
    ]
    if active_columns and "contract_key" not in active_columns:
        LEGACY_TARGET = True
        COLUMNS = [name for name in active_columns if name != "loaded_at"]
        index_columns = [
            row[0]
            for row in client.query(
                "SELECT name FROM system.columns WHERE database = currentDatabase() "
                "AND table = 'dxbi_rental_unit_candidates' ORDER BY position"
            ).result_rows
        ]
        if not index_columns:
            raise RuntimeError("The active v1 rental candidate table is missing")
        expressions = {
            "unit_candidate_key": "unit_candidate_key",
            "observed_contracts": "toUInt32(count())",
            "last_scraped_at": "max(scraped_at)",
            "loaded_at": "now64(3)",
        }
        values = [
            expressions.get(
                name,
                f"argMax({name}, tuple(lease_start, lease_end, scraped_at, event_key))",
            )
            for name in index_columns
        ]
        REFRESH_INDEX_SQL = (
            f"INSERT INTO {INDEX_TABLE} ({', '.join(index_columns)}) "
            f"SELECT {', '.join(values)} FROM {TABLE} FINAL "
            "WHERE lease_start >= toDate('2025-01-01') GROUP BY unit_candidate_key"
        )


def refresh_candidate_index(client) -> None:
    """Rebuild the candidate projection so removed or corrected candidates cannot linger."""
    logger.info("Refreshing %s", INDEX_TABLE)
    client.command(CREATE_INDEX_SQL)
    staging = f"{INDEX_TABLE}_refresh"
    client.command(f"DROP TABLE IF EXISTS {staging}")
    client.command(f"CREATE TABLE {staging} AS {INDEX_TABLE}")
    columns = [
        row[0]
        for row in client.query(
            "SELECT name FROM system.columns WHERE database=currentDatabase() "
            "AND table={table:String} AND default_kind != 'ALIAS' ORDER BY position",
            parameters={"table": INDEX_TABLE},
        ).result_rows
    ]
    aggregates = {
        "unit_candidate_key": "unit_candidate_key",
        "observed_contracts": "toUInt32(contract_count)",
        "last_scraped_at": "last_scraped_at",
        "loaded_at": "now64(3)",
    }
    latest_columns = [name for name in columns if name not in aggregates]
    projection = [
        aggregates.get(name, f"latest.{latest_columns.index(name) + 1}")
        if name in latest_columns
        else aggregates[name]
        for name in columns
    ]
    # One tuple keeps fields from the same latest event and avoids duplicating
    # the large ordering key in a separate argMax state for every column.
    client.command(
        f"INSERT INTO {staging} ({', '.join(columns)}) "
        f"SELECT {', '.join(projection)} FROM ("
        "SELECT unit_candidate_key, "
        f"argMax(tuple({', '.join(latest_columns)}), "
        "tuple(lease_start, lease_end, scraped_at, event_key)) AS latest, "
        f"count() AS contract_count, max(scraped_at) AS last_scraped_at FROM {TABLE} FINAL "
        "WHERE lease_start >= toDate('2025-01-01') GROUP BY unit_candidate_key) "
        "SETTINGS max_threads=2, max_bytes_before_external_group_by=100000000, "
        "max_memory_usage=3000000000"
    )
    client.command(f"EXCHANGE TABLES {INDEX_TABLE} AND {staging}")
    client.command(f"DROP TABLE {staging}")


def _partition_counts(inputs: list[Path]) -> tuple[int, int, int, str]:
    expected = completed = failed = 0
    manifest_hashes: set[str] = set()
    for input_path in inputs:
        path = input_path if input_path.is_dir() else input_path.parent
        reconciliation_path = path / "reconciliation.json"
        if not reconciliation_path.exists():
            checkpoint_path = path / "checkpoint.json"
            if checkpoint_path.exists():
                checkpoint = json.loads(checkpoint_path.read_text())
                done = len(checkpoint.get("completed", {}))
                unfinished = len(checkpoint.get("failed", {})) + len(checkpoint.get("paged", {}))
                expected += done + unfinished
                completed += done
                failed += unfinished
            continue
        payload = json.loads(reconciliation_path.read_text())
        expected += int(payload.get("expected_partitions") or 0)
        completed += int(payload.get("completed_partitions") or 0)
        failed += int(payload.get("failed_partitions") or 0)
        if payload.get("manifest_hash"):
            manifest_hashes.add(str(payload["manifest_hash"]))
    return expected, completed, failed, ",".join(sorted(manifest_hashes))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _record_reconciliation(client, reconciliation: dict[str, Any]) -> None:
    client.command(CREATE_RECONCILIATION_SQL)
    columns = [
        "run_id",
        "report_type",
        "status",
        "raw_rows",
        "unique_source_rows",
        "normalized_rows",
        "quarantined_rows",
        "profile_overlap_rows",
        "loaded_contracts",
        "out_of_scope_rows",
        "expected_partitions",
        "completed_partitions",
        "failed_partitions",
        "manifest_hash",
        "details_json",
        "started_at",
        "finished_at",
    ]
    client.insert(
        RECONCILIATION_TABLE,
        [[reconciliation[column] for column in columns]],
        column_names=columns,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--host", default=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CLICKHOUSE_PORT", "8123")))
    parser.add_argument("--database", default=os.getenv("CLICKHOUSE_DATABASE", "vitevue"))
    parser.add_argument("--username", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--min-start-date", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--quarantine-output", type=Path)
    parser.add_argument("--reconciliation-output", type=Path)
    parser.add_argument("--allow-quarantine", action="store_true")
    parser.add_argument(
        "--target",
        choices=("auto", "shadow", "active"),
        default="auto",
        help="Auto writes v2 before cutover and canonical tables after contract_key is active.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    started_at = datetime.now(timezone.utc)
    files = discover_files(args.inputs)
    if not files:
        raise SystemExit("No JSONL rental shards found")
    logger.info("Discovered %s shards", len(files))
    client = clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        database=args.database,
        username=args.username,
        password=args.password,
    )
    configure_target(client, args.target)
    client.command(CREATE_TABLE_SQL)
    if not LEGACY_TARGET:
        client.command(
            f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS source_cohort_size UInt32 DEFAULT 0"
        )
    quarantine_output = args.quarantine_output
    if quarantine_output is None and args.reconciliation_output:
        quarantine_output = args.reconciliation_output.with_name("rental_quarantine.jsonl")
    totals = load_files(
        files,
        client=client,
        min_start_date=args.min_start_date,
        batch_size=args.batch_size,
        quarantine_path=quarantine_output,
    )
    refresh_candidate_index(client)
    expected, completed, failed, manifest_hash = _partition_counts(args.inputs)
    status = "success"
    if failed or (expected and completed != expected) or totals["quarantined_rows"]:
        status = "failed"
    finished_at = datetime.now(timezone.utc)
    reconciliation: dict[str, Any] = {
        "run_id": args.run_id or f"rental-v2-{finished_at.strftime('%Y%m%dT%H%M%SZ')}",
        "report_type": "rentals",
        "status": status,
        **totals,
        "expected_partitions": expected,
        "completed_partitions": completed,
        "failed_partitions": failed,
        "manifest_hash": manifest_hash,
        "details_json": json.dumps({"inputs": [str(path) for path in args.inputs]}),
        "started_at": started_at,
        "finished_at": finished_at,
    }
    _record_reconciliation(client, reconciliation)
    if args.reconciliation_output:
        _atomic_json(
            args.reconciliation_output,
            {key: value for key, value in reconciliation.items() if key != "details_json"}
            | {"inputs": [str(path) for path in args.inputs]},
        )
    logger.info("Complete %s", json.dumps(totals, sort_keys=True))
    if totals["quarantined_rows"] and not args.allow_quarantine:
        return 1
    return 1 if failed or (expected and completed != expected) else 0


if __name__ == "__main__":
    raise SystemExit(main())
