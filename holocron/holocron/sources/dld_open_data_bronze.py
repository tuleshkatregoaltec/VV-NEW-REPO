from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from holocron.contracts import (
    BronzeLoadResult,
    BronzeLoader,
    ClickHouseInserter,
    RawFileStore,
    RawManifest,
)
from holocron.platform.bronze import (
    bronze_load_result,
    coerce_int,
    iso_date_or_none,
    replace_keyed_rows,
    replace_where_rows,
    stable_json,
    validate_raw_manifest,
)
from holocron.platform.clickhouse import quote_clickhouse_identifier, sql_string
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.manifests import manifest_s3_key
from holocron.platform.raw_files import (
    download_manifest_file,
    manifest_files_by_name,
    read_jsonl_manifest_rows,
    require_manifest_file,
    string_value,
)

_KEY_SEPARATOR = "|"
_SOURCE_SYSTEM = "dld_open_data"
_PROVENANCE_COLUMNS = (
    "source_system",
    "source_file",
    "source_row_index",
    "raw_manifest_s3_key",
)


def dld_row_key(raw_row: dict[str, Any]) -> str:
    raw_payload = raw_row.get("raw")
    return hashlib.sha1(
        _KEY_SEPARATOR.join(
            [
                string_value(raw_row.get("category")),
                string_value(raw_row.get("endpoint")),
                string_value(raw_row.get("row_index")),
                stable_json(raw_payload),
            ]
        ).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()


def dld_envelope_tuple(
    raw_row: dict[str, Any],
    *,
    row_key: str,
    fallback_run_id: str,
) -> tuple:
    window_meta = raw_row.get("date_window") or {}
    return (
        row_key,
        fallback_run_id,
        string_value(raw_row.get("scraped_at")),
        string_value(raw_row.get("mode")),
        iso_date_or_none(window_meta.get("start_date")),
        iso_date_or_none(window_meta.get("end_date")),
        max(coerce_int(raw_row.get("page_index")), 0),
        max(coerce_int(raw_row.get("row_index")), 0),
    )


def build_open_data_bronze_loader(
    *,
    source_name: str,
    column_names: tuple[str, ...],
    row_builder: Callable[..., tuple[Any, ...]],
    replace_date_column: str | None = None,
    replace_date_columns: tuple[str, ...] = (),
) -> BronzeLoader:
    def load_release_to_clickhouse(
        *, raw_manifest: RawManifest, s3: RawFileStore, clickhouse: ClickHouseInserter
    ) -> BronzeLoadResult:
        return load_open_data_release_to_clickhouse(
            raw_manifest=raw_manifest,
            s3=s3,
            clickhouse=clickhouse,
            source_name=source_name,
            table_name=f"{source_name}_bronze",
            row_file_name=f"{source_name}_rows.jsonl",
            column_names=column_names,
            row_builder=row_builder,
            replace_date_column=replace_date_column,
            replace_date_columns=replace_date_columns,
        )

    return load_release_to_clickhouse


def load_open_data_release_to_clickhouse(
    *,
    raw_manifest: RawManifest,
    s3: RawFileStore,
    clickhouse: ClickHouseInserter,
    source_name: str,
    table_name: str,
    row_file_name: str,
    column_names: tuple[str, ...],
    row_builder: Callable[..., tuple[Any, ...]],
    replace_date_column: str | None = None,
    replace_date_columns: tuple[str, ...] = (),
) -> BronzeLoadResult:
    actual_source, run_id = validate_raw_manifest(raw_manifest, expected_source=source_name)
    _require_loadable_result_set(raw_manifest=raw_manifest, source_name=source_name)
    files_by_name = manifest_files_by_name(raw_manifest)
    raw_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []
    page_file_name = row_file_name.replace("_rows.jsonl", "_pages.jsonl")
    with TemporaryDirectory(prefix=f"holocron-{source_name}-bronze-{run_id}-") as scratch:
        scratch_path = Path(scratch)
        row_file_entry = require_manifest_file(files_by_name, row_file_name)
        row_path = download_manifest_file(
            file_name=row_file_name,
            file_entry=row_file_entry,
            s3=s3,
            scratch_path=scratch_path,
            source_label=source_name,
        )
        raw_rows = read_jsonl_manifest_rows(
            path=row_path,
            file_entry=row_file_entry,
            source_label=source_name,
        )
        page_file_entry = files_by_name.get(page_file_name)
        if page_file_entry is not None:
            page_path = download_manifest_file(
                file_name=page_file_name,
                file_entry=page_file_entry,
                s3=s3,
                scratch_path=scratch_path,
                source_label=source_name,
            )
            page_rows = read_jsonl_manifest_rows(
                path=page_path,
                file_entry=page_file_entry,
                source_label=source_name,
            )
    raw_manifest_key = _raw_manifest_key(raw_manifest=raw_manifest, source=actual_source)
    table_rows = [
        (
            *row_builder(raw_row, fallback_run_id=run_id),
            _SOURCE_SYSTEM,
            row_file_name,
            max(coerce_int(raw_row.get("row_index")), 0),
            raw_manifest_key,
        )
        for raw_row in raw_rows
    ]
    load_column_names = (*column_names, *_PROVENANCE_COLUMNS)
    source_scope = f"source_system = {sql_string(_SOURCE_SYSTEM)}"
    configured_replace_date_column = _raw_manifest_replace_date_column(raw_manifest)
    delete_predicate = _open_data_delete_predicate(
        source_name=source_name,
        raw_rows=raw_rows,
        page_rows=page_rows,
        replace_date_column=configured_replace_date_column or replace_date_column,
        replace_date_columns=replace_date_columns,
    )

    ensure_schema(clickhouse=clickhouse)
    if delete_predicate is None:
        replace_keyed_rows(
            clickhouse=clickhouse,
            table=table_name,
            key_column="row_key",
            key_values=[row[0] for row in table_rows],
            rows=table_rows,
            column_names=load_column_names,
            delete_scope=source_scope,
        )
    else:
        replace_where_rows(
            clickhouse=clickhouse,
            table=table_name,
            predicate=f"{source_scope} AND ({delete_predicate})",
            rows=table_rows,
            column_names=load_column_names,
        )

    return bronze_load_result(
        source=actual_source,
        run_id=run_id,
        table_row_counts={table_name: len(table_rows)},
    )


def _require_loadable_result_set(*, raw_manifest: RawManifest, source_name: str) -> None:
    metadata = raw_manifest.get("metadata")
    if not isinstance(metadata, dict):
        return
    if metadata.get("completed_result_set") is False and metadata.get("stage") not in {
        "snapshot",
        "backfill",
    }:
        raise ValueError(
            f"{source_name} incomplete raw result set cannot be loaded into current-state bronze"
        )


def _raw_manifest_key(*, raw_manifest: RawManifest, source: str) -> str:
    explicit_key = string_value(raw_manifest.get("manifest_s3_key"))
    if explicit_key:
        return explicit_key
    return manifest_s3_key(source=source, run_id=string_value(raw_manifest.get("run_id")))


def _raw_manifest_replace_date_column(raw_manifest: RawManifest) -> str:
    metadata = raw_manifest.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    config = metadata.get("config")
    if not isinstance(config, dict):
        return ""
    return string_value(config.get("replace_date_column"))


def _open_data_delete_predicate(
    *,
    source_name: str,
    raw_rows: list[dict[str, Any]],
    page_rows: list[dict[str, Any]],
    replace_date_column: str | None,
    replace_date_columns: tuple[str, ...],
) -> str | None:
    windows = _open_data_start_windows(page_rows=page_rows)
    if not page_rows:
        windows = _open_data_windows(raw_rows=raw_rows, page_rows=page_rows)
    if not windows and page_rows:
        return None
    if not windows:
        raise ValueError(
            f"{source_name} raw manifest has no date-window/page metadata for current-state bronze"
        )
    if any(start is None or end is None for start, end in windows):
        return "1 = 1"
    candidate_date_columns = (
        *replace_date_columns,
        *((replace_date_column,) if replace_date_column else ()),
    )
    date_columns = tuple(dict.fromkeys(candidate_date_columns))
    if date_columns:
        quoted_date_columns = tuple(quote_clickhouse_identifier(column) for column in date_columns)
        return " OR ".join(
            " OR ".join(
                (
                    f"(toDate({quoted_date_column}) >= {_date_sql(start)} "
                    f"AND toDate({quoted_date_column}) <= {_date_sql(end)})"
                )
                for quoted_date_column in quoted_date_columns
            )
            for start, end in windows
        )
    return " OR ".join(
        f"(date_window_start = {_date_sql(start)} AND date_window_end = {_date_sql(end)})"
        for start, end in windows
    )


def _open_data_start_windows(
    *,
    page_rows: list[dict[str, Any]],
) -> tuple[tuple[str | None, str | None], ...]:
    windows: list[tuple[str | None, str | None]] = []
    for row in page_rows:
        if coerce_int(row.get("skip")) != 0:
            continue
        windows.append(_open_data_window(row))
    return tuple(dict.fromkeys(windows))


def _open_data_windows(
    *,
    raw_rows: list[dict[str, Any]],
    page_rows: list[dict[str, Any]],
) -> tuple[tuple[str | None, str | None], ...]:
    windows: list[tuple[str | None, str | None]] = []
    for row in (*page_rows, *raw_rows):
        windows.append(_open_data_window(row))
    return tuple(dict.fromkeys(windows))


def _open_data_window(row: dict[str, Any]) -> tuple[str | None, str | None]:
    window = row.get("date_window")
    if window is None:
        return (None, None)
    if not isinstance(window, dict):
        return (None, None)
    start = string_value(window.get("start_date")) or None
    end = string_value(window.get("end_date")) or None
    return (start, end)


def _date_sql(value: str | None) -> str:
    if value is None:
        return "NULL"
    return f"toDate({sql_string(date.fromisoformat(value).isoformat())})"
