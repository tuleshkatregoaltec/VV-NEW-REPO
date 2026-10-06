from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from holocron.contracts import (
    BronzeLoadResult,
    ClickHouseInserter,
    RawFileStore,
    RawManifest,
    RawManifestFile,
)
from holocron.platform.clickhouse import quote_clickhouse_identifier, sql_string
from holocron.platform.raw_files import (
    download_manifest_file,
    read_jsonl_manifest_rows,
    require_manifest_file,
    string_value,
)

_FALSE_STRINGS = {"", "0", "false", "no", "n", "none"}
_MAX_REPLACE_KEYED_DELETE_BYTES = 200_000


def validate_raw_manifest(raw_manifest: RawManifest, *, expected_source: str) -> tuple[str, str]:
    source_name = string_value(raw_manifest.get("source"))
    if source_name != expected_source:
        raise ValueError(f"Expected raw_manifest.source={expected_source}, got {source_name!r}")

    run_id = string_value(raw_manifest.get("run_id"))
    if not run_id:
        raise ValueError("raw_manifest.run_id is required")
    return source_name, run_id


def bronze_load_result(
    *,
    source: str,
    run_id: str,
    table_row_counts: Mapping[str, int],
) -> BronzeLoadResult:
    counts = dict(table_row_counts)
    return {
        "source": source,
        "run_id": run_id,
        "table_row_counts": counts,
        "table_count": len(counts),
        "total_rows": sum(counts.values()),
    }


def load_jsonl_table_rows(
    *,
    files_by_name: Mapping[str, RawManifestFile],
    file_name: str,
    s3: RawFileStore,
    run_id: str,
    source_label: str,
    row_builder: Callable[..., tuple[Any, ...]],
    required: bool = False,
    scratch_prefix: str = "holocron-bronze",
) -> list[tuple[Any, ...]]:
    file_entry = (
        require_manifest_file(files_by_name, file_name)
        if required
        else files_by_name.get(file_name)
    )
    if file_entry is None:
        return []

    with TemporaryDirectory(prefix=f"{scratch_prefix}-{run_id}-") as scratch:
        local_path = download_manifest_file(
            file_name=file_name,
            file_entry=file_entry,
            s3=s3,
            scratch_path=Path(scratch),
            source_label=source_label,
        )
        return [
            row_builder(raw_row, fallback_run_id=run_id)
            for raw_row in read_jsonl_manifest_rows(
                path=local_path,
                file_entry=file_entry,
                source_label=source_label,
            )
        ]


def replace_run_rows(
    *,
    clickhouse: ClickHouseInserter,
    table: str,
    run_id: str,
    rows: Sequence[tuple[Any, ...]],
    column_names: Sequence[str],
) -> None:
    quoted_table = quote_clickhouse_identifier(table)
    clickhouse.command(
        f"ALTER TABLE {quoted_table} DELETE WHERE run_id = {sql_string(run_id)} "
        "SETTINGS mutations_sync = 1"
    )
    if rows:
        clickhouse.insert_rows(table=table, rows=rows, column_names=column_names)


def replace_where_rows(
    *,
    clickhouse: ClickHouseInserter,
    table: str,
    predicate: str,
    rows: Sequence[tuple[Any, ...]],
    column_names: Sequence[str],
) -> None:
    quoted_table = quote_clickhouse_identifier(table)
    clickhouse.command(
        f"ALTER TABLE {quoted_table} DELETE WHERE {predicate} SETTINGS mutations_sync = 1"
    )
    if rows:
        clickhouse.insert_rows(table=table, rows=rows, column_names=column_names)


def replace_keyed_rows(
    *,
    clickhouse: ClickHouseInserter,
    table: str,
    key_column: str,
    key_values: Sequence[str],
    rows: Sequence[tuple[Any, ...]],
    column_names: Sequence[str],
    delete_scope: str = "",
) -> None:
    keys = tuple(dict.fromkeys(key for key in key_values if key))
    if not keys:
        if rows:
            clickhouse.insert_rows(table=table, rows=rows, column_names=column_names)
        return
    quoted_key_column = quote_clickhouse_identifier(key_column)
    for key_batch in _chunk_key_values(
        quoted_key_column=quoted_key_column,
        keys=keys,
    ):
        quoted_values = ", ".join(sql_string(key) for key in key_batch)
        key_predicate = f"{quoted_key_column} IN ({quoted_values})"
        predicate = f"({delete_scope}) AND ({key_predicate})" if delete_scope else key_predicate
        replace_where_rows(
            clickhouse=clickhouse,
            table=table,
            predicate=predicate,
            rows=(),
            column_names=column_names,
        )
    if rows:
        clickhouse.insert_rows(table=table, rows=rows, column_names=column_names)


def _chunk_key_values(
    *,
    quoted_key_column: str,
    keys: Sequence[str],
) -> list[tuple[str, ...]]:
    batches: list[tuple[str, ...]] = []
    current: list[str] = []
    current_size = len(f"{quoted_key_column} IN ()")
    for key in keys:
        literal = sql_string(key)
        extra_size = len(literal) + (2 if current else 0)
        if current and current_size + extra_size > _MAX_REPLACE_KEYED_DELETE_BYTES:
            batches.append(tuple(current))
            current = []
            current_size = len(f"{quoted_key_column} IN ()")
            extra_size = len(literal)
        current.append(key)
        current_size += extra_size
    if current:
        batches.append(tuple(current))
    return batches


def coerce_int(value: Any) -> int:
    parsed = string_value(value)
    if not parsed:
        return 0
    try:
        return int(parsed)
    except ValueError:
        return int(float(parsed))


def coerce_nullable_int(value: Any) -> int | None:
    parsed = string_value(value)
    if not parsed:
        return None
    try:
        return int(parsed)
    except ValueError:
        return int(float(parsed))


def coerce_float(value: Any) -> float:
    parsed = string_value(value).replace(",", "")
    if not parsed:
        return 0.0
    return float(parsed)


def coerce_float_or_none(value: Any) -> float | None:
    parsed = string_value(value)
    if not parsed:
        return None
    return float(parsed)


def coerce_boolish_uint8(value: Any) -> int:
    parsed = string_value(value).lower()
    return 0 if parsed in _FALSE_STRINGS else 1


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def iso_date_or_none(value: Any) -> date | None:
    parsed = string_value(value)
    if not parsed:
        return None
    return date.fromisoformat(parsed)


_EPOCH = datetime(1970, 1, 1)


def iso_datetime_or_default(value: Any) -> datetime:
    parsed = string_value(value)
    if not parsed:
        return _EPOCH
    try:
        return datetime.fromisoformat(parsed)
    except (ValueError, TypeError):
        return _EPOCH


def iso_datetime_or_none(value: Any) -> datetime | None:
    parsed = string_value(value)
    if not parsed:
        return None
    try:
        return datetime.fromisoformat(parsed)
    except (ValueError, TypeError):
        return None
