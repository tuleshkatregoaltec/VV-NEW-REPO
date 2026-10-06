from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from holocron.contracts import (
    BronzeReplayStore,
    ClickHouseInserter,
    ClickHouseWriter,
    ObjectLister,
    SourceSpec,
)
from holocron.platform.clickhouse import ClickHouseClient, quote_clickhouse_identifier
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.dataset_versions import (
    DATASET_VERSION_REPLAY_STRATEGY,
    DatasetVersionSelection,
    read_dataset_version,
)
from holocron.platform.manifests import (
    manifest_s3_key,
    raw_manifest_prefix,
    require_normal_raw_manifest,
)
from holocron.platform.raw_files import read_and_validate_manifest, string_value
from holocron.platform.object_storage import ObjectStorageClient
from holocron.platform.settings import settings
from holocron.sources import registry

_BRONZE_LOAD_LEDGER_TABLE = "bronze_load_ledger"
_BRONZE_LOAD_LEDGER_COLUMNS = (
    "source",
    "dataset_version",
    "manifest_key",
    "run_id",
    "table_name",
    "row_count",
    "loaded_at",
    "status",
    "error",
)


def replay_bronze_manifests(
    *,
    source_name: str,
    s3: BronzeReplayStore,
    clickhouse: ClickHouseWriter,
    manifest_keys: Sequence[str] = (),
    manifest_prefix: str | None = None,
    latest_count: int | None = None,
    limit: int | None = None,
    dataset_version: str | None = None,
    dry_run: bool = False,
    initial_load: bool = False,
) -> dict[str, Any]:
    source = registry.get(source_name)
    _validate_replay_source(source)

    dataset_selection: DatasetVersionSelection | None = None
    if dataset_version:
        _validate_dataset_version_replay_args(
            dataset_version=dataset_version,
            manifest_keys=manifest_keys,
            manifest_prefix=manifest_prefix,
            latest_count=latest_count,
            limit=limit,
            initial_load=initial_load,
        )
        dataset_selection = read_dataset_version(
            s3=s3,
            source=source,
            identifier=dataset_version,
            require_complete=True,
        )
        selected_manifest_keys = list(dataset_selection.manifest_keys)
    else:
        selected_manifest_keys = select_manifest_keys(
            s3=s3,
            source_name=source.name,
            manifest_keys=manifest_keys,
            manifest_prefix=manifest_prefix,
            latest_count=latest_count,
            limit=limit,
        )
    manifests = []
    for manifest_key in selected_manifest_keys:
        manifest = read_and_validate_manifest(
            s3=s3,
            source_name=source.name,
            manifest_key=manifest_key,
        )
        require_normal_raw_manifest(
            source=source.name,
            manifest_key=manifest_key,
            manifest=manifest,
        )
        manifests.append(manifest)

    manifest_summaries = [
        {
            "manifest_s3_key": manifest_key,
            "run_id": manifest["run_id"],
            "extract_date": manifest.get("extract_date", ""),
            "file_count": len(manifest["files"]),
            "manifest_row_count": sum(
                int(file_entry.get("row_count") or 0) for file_entry in manifest["files"]
            ),
        }
        for manifest_key, manifest in zip(selected_manifest_keys, manifests, strict=True)
    ]
    dataset_version_summary = _dataset_version_summary(dataset_selection)
    if dry_run:
        return {
            "source": source.name,
            "dry_run": True,
            "initial_load": initial_load,
            **dataset_version_summary,
            "manifest_count": len(manifests),
            "manifests": manifest_summaries,
            "table_count": len(source.bronze_tables),
            "total_rows": 0,
            "table_row_counts": {},
            "failures": [],
            "ledger_rows": 0,
        }

    ensure_schema(clickhouse=clickhouse)
    clickhouse_for_loader = clickhouse
    truncated_tables: list[str] = []
    if initial_load:
        truncated_tables = [table.name for table in source.bronze_tables]
        for table_name in truncated_tables:
            clickhouse.command(f"TRUNCATE TABLE {quote_clickhouse_identifier(table_name)}")
        clickhouse_for_loader = _InitialLoadClickHouse(
            inner=clickhouse,
            skip_delete_tables=truncated_tables,
        )
    table_row_counts: dict[str, int] = {}
    loaded_manifests: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    ledger_rows = 0
    bronze_loader = source.bronze_loader
    if bronze_loader is None:
        raise ValueError(f"No bronze loader configured for source={source.name}")
    for manifest_key, manifest in zip(selected_manifest_keys, manifests, strict=True):
        try:
            result = bronze_loader(
                raw_manifest=manifest,
                s3=s3,
                clickhouse=clickhouse_for_loader,
            )
        except Exception as exc:  # noqa: BLE001 - replay reports per-manifest failures.
            failures.append({"manifest_s3_key": manifest_key, "error": str(exc)})
            if dataset_selection is not None:
                ledger_rows += _write_ledger_failure(
                    clickhouse=clickhouse,
                    source_name=source.name,
                    dataset_version=dataset_selection.dataset_version,
                    manifest_key=manifest_key,
                    run_id=string_value(manifest.get("run_id")),
                    error=str(exc),
                )
            continue

        for table_name, row_count in result.get("table_row_counts", {}).items():
            table_row_counts[table_name] = table_row_counts.get(table_name, 0) + int(row_count)
        if dataset_selection is not None:
            ledger_rows += _write_ledger_success(
                clickhouse=clickhouse,
                source_name=source.name,
                dataset_version=dataset_selection.dataset_version,
                manifest_key=manifest_key,
                run_id=string_value(result.get("run_id") or manifest["run_id"]),
                table_row_counts=result.get("table_row_counts", {}),
            )
        loaded_manifests.append(
            {
                "manifest_s3_key": manifest_key,
                "run_id": result.get("run_id", manifest["run_id"]),
                "table_row_counts": dict(result.get("table_row_counts", {})),
                "total_rows": int(result.get("total_rows") or 0),
            }
        )

    return {
        "source": source.name,
        "dry_run": False,
        "initial_load": initial_load,
        **dataset_version_summary,
        "truncated_tables": truncated_tables,
        "skipped_delete_count": getattr(clickhouse_for_loader, "skipped_delete_count", 0),
        "manifest_count": len(manifests),
        "manifests": manifest_summaries,
        "loaded_manifests": loaded_manifests,
        "table_count": len(table_row_counts),
        "total_rows": sum(table_row_counts.values()),
        "table_row_counts": table_row_counts,
        "failures": failures,
        "ledger_rows": ledger_rows,
    }


class _InitialLoadClickHouse:
    def __init__(self, *, inner: Any, skip_delete_tables: Sequence[str]) -> None:
        self._inner = inner
        self._skip_delete_prefixes = tuple(
            f"ALTER TABLE {quote_clickhouse_identifier(table)} DELETE WHERE "
            for table in skip_delete_tables
        )
        self.skipped_delete_count = 0

    def command(self, sql: str) -> Any:
        if sql.startswith(self._skip_delete_prefixes):
            self.skipped_delete_count += 1
            return None
        return self._inner.command(sql)

    def query(self, sql: str) -> Any:
        return self._inner.query(sql)

    def insert_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
    ) -> None:
        return self._inner.insert_rows(table=table, rows=rows, column_names=column_names)

    def replace_table_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
        staging_suffix: str = "replace_rows",
    ) -> int:
        return self._inner.replace_table_rows(
            table=table,
            rows=rows,
            column_names=column_names,
            staging_suffix=staging_suffix,
        )


def select_manifest_keys(
    *,
    s3: ObjectLister,
    source_name: str,
    manifest_keys: Sequence[str] = (),
    manifest_prefix: str | None = None,
    latest_count: int | None = None,
    limit: int | None = None,
) -> list[str]:
    if latest_count is not None and latest_count <= 0:
        raise ValueError("latest_count must be positive when provided")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive when provided")
    if manifest_keys:
        keys = list(dict.fromkeys(string_value(key) for key in manifest_keys if string_value(key)))
    else:
        prefix = manifest_prefix or raw_manifest_prefix(source=source_name)
        keys = sorted(key for key in s3.list_keys(prefix=prefix) if key.endswith(".json"))
    if latest_count is not None:
        keys = keys[-latest_count:]
    if limit is not None:
        keys = keys[:limit]
    return keys


def _validate_replay_source(source: SourceSpec) -> None:
    if source.bronze_loader is None:
        raise ValueError(f"No bronze loader configured for source={source.name}")
    if not source.bronze_tables:
        raise ValueError(f"No bronze tables configured for source={source.name}")


def _validate_dataset_version_replay_args(
    *,
    dataset_version: str,
    manifest_keys: Sequence[str],
    manifest_prefix: str | None,
    latest_count: int | None,
    limit: int | None,
    initial_load: bool,
) -> None:
    if not initial_load:
        raise ValueError("--dataset-version requires --initial-load")
    mixed_selectors: list[str] = []
    if manifest_keys:
        mixed_selectors.append("--manifest-key/--run-id")
    if manifest_prefix is not None:
        mixed_selectors.append("--manifest-prefix")
    if latest_count is not None:
        mixed_selectors.append("--latest-count")
    if limit is not None:
        mixed_selectors.append("--limit")
    if mixed_selectors:
        joined = ", ".join(mixed_selectors)
        raise ValueError(f"--dataset-version cannot be combined with {joined}")
    if not string_value(dataset_version):
        raise ValueError("--dataset-version must not be blank")


def _dataset_version_summary(selection: DatasetVersionSelection | None) -> dict[str, Any]:
    if selection is None:
        return {
            "dataset_version": None,
            "dataset_version_key": None,
            "dataset_version_status": None,
            "replay_strategy": None,
            "coverage": {},
        }
    return {
        "dataset_version": selection.dataset_version,
        "dataset_version_key": selection.key,
        "dataset_version_status": selection.descriptor["status"],
        "replay_strategy": selection.descriptor.get(
            "replay_strategy", DATASET_VERSION_REPLAY_STRATEGY
        ),
        "coverage": selection.descriptor.get("coverage", {}),
    }


def _write_ledger_success(
    *,
    clickhouse: ClickHouseInserter,
    source_name: str,
    dataset_version: str,
    manifest_key: str,
    run_id: str,
    table_row_counts: Mapping[str, Any],
) -> int:
    if not isinstance(table_row_counts, dict):
        raise ValueError("bronze loader result table_row_counts must be a dict")
    loaded_at = datetime.now(UTC)
    rows = [
        (
            source_name,
            dataset_version,
            manifest_key,
            run_id,
            table_name,
            int(row_count),
            loaded_at,
            "success",
            "",
        )
        for table_name, row_count in table_row_counts.items()
    ]
    if not rows:
        return 0
    clickhouse.insert_rows(
        table=_BRONZE_LOAD_LEDGER_TABLE,
        rows=rows,
        column_names=_BRONZE_LOAD_LEDGER_COLUMNS,
    )
    return len(rows)


def _write_ledger_failure(
    *,
    clickhouse: ClickHouseInserter,
    source_name: str,
    dataset_version: str,
    manifest_key: str,
    run_id: str,
    error: str,
) -> int:
    clickhouse.insert_rows(
        table=_BRONZE_LOAD_LEDGER_TABLE,
        rows=[
            (
                source_name,
                dataset_version,
                manifest_key,
                run_id,
                "",
                0,
                datetime.now(UTC),
                "failure",
                error,
            )
        ],
        column_names=_BRONZE_LOAD_LEDGER_COLUMNS,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay existing raw manifests into ClickHouse bronze tables."
    )
    parser.add_argument("source", help="Source name to replay, for example dld_od_transactions.")
    parser.add_argument(
        "--manifest-key",
        action="append",
        default=[],
        help="Explicit raw manifest S3 key. May be provided multiple times.",
    )
    parser.add_argument(
        "--manifest-prefix",
        default=None,
        help="Manifest key prefix. Defaults to raw/source=<source>/manifests/.",
    )
    parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        help="Convenience selector for raw/source=<source>/manifests/<run-id>.json.",
    )
    parser.add_argument("--latest-count", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--dataset-version",
        default=None,
        help=(
            "Replay the ordered manifests from a dataset version descriptor. Use "
            "latest_complete or a raw/source=<source>/dataset_versions/<id>.json key."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--initial-load",
        action="store_true",
        help=(
            "Truncate the source bronze tables first and skip per-manifest DELETE mutations. "
            "Use only when rebuilding those tables from the selected manifests."
        ),
    )
    args = parser.parse_args(argv)

    explicit_keys = [
        *args.manifest_key,
        *(manifest_s3_key(source=args.source, run_id=run_id) for run_id in args.run_id),
    ]
    result = replay_bronze_manifests(
        source_name=args.source,
        s3=ObjectStorageClient(settings),
        clickhouse=ClickHouseClient(settings),
        manifest_keys=explicit_keys,
        manifest_prefix=args.manifest_prefix,
        latest_count=args.latest_count,
        limit=args.limit,
        dataset_version=args.dataset_version,
        dry_run=args.dry_run,
        initial_load=args.initial_load,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
