from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from holocron.contracts import ClickHouseCommands, ManifestStore, RawManifest
from holocron.platform.clickhouse import ClickHouseClient, quote_clickhouse_identifier, sql_string
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.raw_files import manifest_files_by_name, string_value
from holocron.platform.object_storage import ObjectStorageClient
from holocron.platform.settings import settings

_DLD_OPEN_DATA_SOURCE_SYSTEM = "dld_open_data"
_DLD_PULSE_SOURCE = "dld_pulse_historic"
_DLD_PULSE_SOURCE_SYSTEM = "dubai_pulse"

_DLD_OPEN_DATA_SOURCES = (
    "dld_od_transactions",
    "dld_od_rents",
    "dld_od_projects",
    "dld_od_valuations",
    "dld_od_lands",
    "dld_od_buildings",
    "dld_od_units",
    "dld_od_brokers",
    "dld_od_developers",
)

_DLD_PULSE_FILE_TABLES = {
    "developers.csv": "dld_od_developers_bronze",
    "projects.csv": "dld_od_projects_bronze",
    "lands.csv": "dld_od_lands_bronze",
    "buildings.csv": "dld_od_buildings_bronze",
    "units.csv": "dld_od_units_bronze",
    "transactions.csv": "dld_od_transactions_bronze",
    "rent_contracts.csv": "dld_od_rents_bronze",
}


@dataclass(frozen=True, slots=True)
class ProvenanceBackfillStatement:
    source: str
    table: str
    source_system: str
    manifest_key: str
    sql: str


def build_dld_provenance_backfill_statements(
    *,
    s3: ManifestStore,
    include_open_data: bool = True,
    include_pulse: bool = True,
    sources: Sequence[str] = _DLD_OPEN_DATA_SOURCES,
) -> list[ProvenanceBackfillStatement]:
    statements: list[ProvenanceBackfillStatement] = []
    if include_open_data:
        for source in sources:
            statements.extend(_open_data_statements(s3=s3, source=source))
    if include_pulse:
        statements.extend(_pulse_statements(s3=s3))
    return statements


def run_dld_provenance_backfill(
    *,
    s3: ManifestStore,
    clickhouse: ClickHouseCommands,
    execute: bool,
    include_open_data: bool = True,
    include_pulse: bool = True,
    sources: Sequence[str] = _DLD_OPEN_DATA_SOURCES,
) -> dict[str, Any]:
    if execute:
        ensure_schema(clickhouse=clickhouse)
    statements = build_dld_provenance_backfill_statements(
        s3=s3,
        include_open_data=include_open_data,
        include_pulse=include_pulse,
        sources=sources,
    )
    if execute:
        for statement in statements:
            clickhouse.command(statement.sql)
    by_source_system: dict[str, int] = {}
    for statement in statements:
        by_source_system[statement.source_system] = (
            by_source_system.get(statement.source_system, 0) + 1
        )
    return {
        "dry_run": not execute,
        "statement_count": len(statements),
        "source_system_counts": by_source_system,
        "statements": [
            {
                "source": statement.source,
                "table": statement.table,
                "source_system": statement.source_system,
                "manifest_key": statement.manifest_key,
                "sql": statement.sql,
            }
            for statement in statements
        ],
    }


def _open_data_statements(*, s3: ManifestStore, source: str) -> list[ProvenanceBackfillStatement]:
    row_file_name = f"{source}_rows.jsonl"
    table = f"{source}_bronze"
    statements: list[ProvenanceBackfillStatement] = []
    for manifest_key in sorted(s3.list_keys(prefix=f"raw/source={source}/manifests/")):
        if not manifest_key.endswith(".json"):
            continue
        manifest = _manifest_for_key(s3=s3, manifest_key=manifest_key)
        _require_manifest_source(
            manifest=manifest, expected_source=source, manifest_key=manifest_key
        )
        if row_file_name not in manifest_files_by_name(manifest):
            continue
        run_id = _require_run_id(manifest=manifest, manifest_key=manifest_key)
        statements.append(
            ProvenanceBackfillStatement(
                source=source,
                table=table,
                source_system=_DLD_OPEN_DATA_SOURCE_SYSTEM,
                manifest_key=manifest_key,
                sql=_open_data_update_sql(
                    table=table,
                    run_id=run_id,
                    row_file_name=row_file_name,
                    manifest_key=manifest_key,
                ),
            )
        )
    return statements


def _pulse_statements(*, s3: ManifestStore) -> list[ProvenanceBackfillStatement]:
    statements: list[ProvenanceBackfillStatement] = []
    for manifest_key in sorted(s3.list_keys(prefix=f"raw/source={_DLD_PULSE_SOURCE}/manifests/")):
        if not manifest_key.endswith(".json"):
            continue
        manifest = _manifest_for_key(s3=s3, manifest_key=manifest_key)
        _require_manifest_source(
            manifest=manifest,
            expected_source=_DLD_PULSE_SOURCE,
            manifest_key=manifest_key,
        )
        run_id = _require_run_id(manifest=manifest, manifest_key=manifest_key)
        files_by_name = manifest_files_by_name(manifest)
        for file_name, table in _DLD_PULSE_FILE_TABLES.items():
            if file_name not in files_by_name:
                continue
            statements.append(
                ProvenanceBackfillStatement(
                    source=_DLD_PULSE_SOURCE,
                    table=table,
                    source_system=_DLD_PULSE_SOURCE_SYSTEM,
                    manifest_key=manifest_key,
                    sql=_pulse_update_sql(
                        table=table,
                        run_id=run_id,
                        file_name=file_name,
                        manifest_key=manifest_key,
                    ),
                )
            )
    return statements


def _manifest_for_key(*, s3: ManifestStore, manifest_key: str) -> RawManifest:
    manifest = s3.get_json(key=manifest_key)
    if not isinstance(manifest, dict):
        raise ValueError(f"Raw manifest is missing or not an object: {manifest_key}")
    return manifest


def _require_manifest_source(
    *,
    manifest: Mapping[str, Any],
    expected_source: str,
    manifest_key: str,
) -> None:
    actual_source = string_value(manifest.get("source"))
    if actual_source != expected_source:
        raise ValueError(
            f"Raw manifest source mismatch at {manifest_key}: "
            f"expected={expected_source!r} actual={actual_source!r}"
        )


def _require_run_id(*, manifest: Mapping[str, Any], manifest_key: str) -> str:
    run_id = string_value(manifest.get("run_id"))
    if not run_id:
        raise ValueError(f"Raw manifest is missing run_id: {manifest_key}")
    return run_id


def _open_data_update_sql(
    *,
    table: str,
    run_id: str,
    row_file_name: str,
    manifest_key: str,
) -> str:
    return (
        f"ALTER TABLE {quote_clickhouse_identifier(table)} UPDATE "
        f"raw_manifest_s3_key = {sql_string(manifest_key)}, "
        f"source_file = if(source_file = '', {sql_string(row_file_name)}, source_file), "
        "source_row_index = if(source_row_index = 0, row_index, source_row_index) "
        f"WHERE source_system = {sql_string(_DLD_OPEN_DATA_SOURCE_SYSTEM)} "
        f"AND run_id = {sql_string(run_id)} "
        "AND (raw_manifest_s3_key = '' OR source_file = '' OR source_row_index = 0) "
        "SETTINGS mutations_sync = 1"
    )


def _pulse_update_sql(
    *,
    table: str,
    run_id: str,
    file_name: str,
    manifest_key: str,
) -> str:
    return (
        f"ALTER TABLE {quote_clickhouse_identifier(table)} UPDATE "
        f"raw_manifest_s3_key = {sql_string(manifest_key)} "
        f"WHERE source_system = {sql_string(_DLD_PULSE_SOURCE_SYSTEM)} "
        f"AND run_id = {sql_string(run_id)} "
        f"AND source_file = {sql_string(file_name)} "
        "AND raw_manifest_s3_key = '' "
        "SETTINGS mutations_sync = 1"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill DLD bronze raw_manifest_s3_key provenance pointers."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the ClickHouse mutations. Without this flag the script only reports planned SQL.",
    )
    parser.add_argument(
        "--open-data-only",
        action="store_true",
        help="Only plan DLD open-data table updates.",
    )
    parser.add_argument(
        "--pulse-only",
        action="store_true",
        help="Only plan Dubai Pulse historic table updates.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        choices=_DLD_OPEN_DATA_SOURCES,
        help="Limit open-data updates to one source. May be passed more than once.",
    )
    args = parser.parse_args(argv)
    if args.open_data_only and args.pulse_only:
        parser.error("--open-data-only and --pulse-only cannot be combined")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    include_open_data = not args.pulse_only
    include_pulse = not args.open_data_only
    result = run_dld_provenance_backfill(
        s3=ObjectStorageClient(settings),
        clickhouse=ClickHouseClient(settings),
        execute=bool(args.execute),
        include_open_data=include_open_data,
        include_pulse=include_pulse,
        sources=tuple(args.source) or _DLD_OPEN_DATA_SOURCES,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
