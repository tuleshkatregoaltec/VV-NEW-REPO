from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from holocron.contracts import (
    BronzeLoadResult,
    ClickHouseWriter,
    RawFileStore,
    RawManifest,
)
from holocron.platform.bronze import (
    bronze_load_result,
    coerce_int,
    replace_where_rows,
    stable_json,
    validate_raw_manifest,
)
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.raw_files import (
    download_manifest_file,
    manifest_files_by_name,
    read_jsonl_manifest_rows,
    string_value,
)
from holocron.sources.dxbi.source import DXBI_SOURCE_NAME

_TABLE_NAME = "dxbi_transactions_bronze"
_RENTAL_BUILDINGS_TABLE = "dxbi_heatmap_rental_buildings_bronze"
_BUILDINGS_TABLE = "dxbi_heatmap_buildings_bronze"
_BUILDING_STATUSES_TABLE = "dxbi_heatmap_building_statuses_bronze"
_CHESSBOARDS_TABLE = "dxbi_heatmap_chessboards_bronze"
_FAM_BUILDINGS_TABLE = "dxbi_fam_map_buildings_bronze"
_ERRORS_TABLE = "dxbi_heatmap_errors_bronze"
_TABLE_COLUMNS = (
    "transaction_key",
    "source_table",
    "cells_json",
    "cells_count",
    "run_id",
    "scraped_at",
    "slice_start_date",
    "slice_end_date",
    "source_url",
    "page_number",
    "row_number",
)
_RENTAL_BUILDING_COLUMNS = (
    "rental_key",
    "run_id",
    "scraped_at",
    "location_id",
    "property_type",
    "bedrooms",
    "query_json",
    "raw_json",
)
_ENDPOINT_RESPONSE_COLUMNS = (
    "response_key",
    "run_id",
    "scraped_at",
    "location_id",
    "endpoint",
    "status",
    "request_url",
    "content_type",
    "seed_json",
    "payload_json",
    "text",
)
_ERROR_COLUMNS = (
    "error_key",
    "run_id",
    "scraped_at",
    "location_id",
    "endpoint",
    "status",
    "request_url",
    "request_body_json",
    "content_type",
    "payload_json",
    "text",
)
_HEATMAP_RESPONSE_FILES = {
    "dxbi_heatmap_buildings.jsonl": _BUILDINGS_TABLE,
    "dxbi_heatmap_building_statuses.jsonl": _BUILDING_STATUSES_TABLE,
    "dxbi_heatmap_chessboards.jsonl": _CHESSBOARDS_TABLE,
    "dxbi_fam_map_buildings.jsonl": _FAM_BUILDINGS_TABLE,
}


def _string(value: Any) -> str:
    return string_value(value)


def _int(value: Any) -> int:
    return coerce_int(value)


def _date(value: Any, *, field_name: str) -> date:
    parsed = _string(value)
    if not parsed:
        raise ValueError(f"DXBI row is missing required date field: {field_name}")
    return date.fromisoformat(parsed)


def _row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    source_table = _string(raw_row.get("table"))
    if not source_table:
        raise ValueError("DXBI raw row is missing table")

    raw_cells = raw_row.get("cells")
    if not isinstance(raw_cells, list):
        raise ValueError("DXBI raw row cells must be a list")
    cells = [_string(value) for value in raw_cells]
    cells_json = json.dumps(cells, ensure_ascii=False)
    source_url = _string(raw_row.get("_source_url"))

    transaction_key = hashlib.sha1(
        f"{source_table}|{source_url}|{cells_json}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()

    run_id = _string(raw_row.get("_run_id")) or fallback_run_id
    return (
        transaction_key,
        source_table,
        cells_json,
        min(len(cells), 65535),
        run_id,
        _string(raw_row.get("_scraped_at")),
        _date(raw_row.get("_slice_start_date"), field_name="_slice_start_date"),
        _date(raw_row.get("_slice_end_date"), field_name="_slice_end_date"),
        source_url,
        max(_int(raw_row.get("_page_number")), 0),
        max(_int(raw_row.get("_row_number")), 0),
    )


def _slice_delete_predicate(slices: set[tuple[date, date]]) -> str:
    return " OR ".join(
        "("
        f"slice_start_date = toDate('{start_date.isoformat()}') "
        f"AND slice_end_date = toDate('{end_date.isoformat()}')"
        ")"
        for start_date, end_date in slices
    )


def _report_row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    return _row_tuple(raw_row, fallback_run_id=fallback_run_id)


def _rental_building_row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    query = raw_row.get("query")
    if not isinstance(query, dict):
        query = {}
    location_id = _string(raw_row.get("location_id"))
    property_type = _string(query.get("Type"))
    bedrooms = _string(query.get("Bedrooms"))
    raw_json = stable_json(raw_row.get("raw"))
    rental_key = _hash_key(location_id, property_type, bedrooms, raw_json)
    return (
        rental_key,
        _string(raw_row.get("_run_id")) or fallback_run_id,
        _string(raw_row.get("_scraped_at")),
        location_id,
        property_type,
        bedrooms,
        stable_json(query),
        raw_json,
    )


def _endpoint_response_row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    location_id = _string(raw_row.get("location_id"))
    endpoint = _string(raw_row.get("endpoint"))
    payload_json = stable_json(raw_row.get("payload"))
    response_key = _hash_key(location_id, endpoint)
    return (
        response_key,
        _string(raw_row.get("_run_id")) or fallback_run_id,
        _string(raw_row.get("_scraped_at")),
        location_id,
        endpoint,
        max(_int(raw_row.get("status")), 0),
        _string(raw_row.get("request_url")),
        _string(raw_row.get("content_type")),
        stable_json(raw_row.get("seed")),
        payload_json,
        _string(raw_row.get("text")),
    )


def _error_row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    location_id = _string(raw_row.get("location_id"))
    endpoint = _string(raw_row.get("endpoint"))
    payload_json = stable_json(raw_row.get("payload"))
    text = _string(raw_row.get("text"))
    error_key = _hash_key(
        location_id,
        endpoint,
        _string(raw_row.get("request_url")),
        _string(raw_row.get("request_body")),
        payload_json,
        text,
    )
    return (
        error_key,
        _string(raw_row.get("_run_id")) or fallback_run_id,
        _string(raw_row.get("_scraped_at")),
        location_id,
        endpoint,
        max(_int(raw_row.get("status")), 0),
        _string(raw_row.get("request_url")),
        stable_json(raw_row.get("request_body")),
        _string(raw_row.get("content_type")),
        payload_json,
        text,
    )


def load_release_to_clickhouse(
    *,
    raw_manifest: RawManifest,
    s3: RawFileStore,
    clickhouse: ClickHouseWriter,
) -> BronzeLoadResult:
    source_name, run_id = validate_raw_manifest(raw_manifest, expected_source=DXBI_SOURCE_NAME)

    files_by_name = manifest_files_by_name(raw_manifest)
    jsonl_file_names = sorted(name for name in files_by_name if name.endswith(".jsonl"))
    if not jsonl_file_names:
        raise ValueError("DXBI raw_manifest has no jsonl files")

    report_rows: list[tuple] = []
    report_slices: set[tuple[date, date]] = set()
    heatmap_rows_by_table: dict[str, list[tuple]] = {
        _RENTAL_BUILDINGS_TABLE: [],
        _BUILDINGS_TABLE: [],
        _BUILDING_STATUSES_TABLE: [],
        _CHESSBOARDS_TABLE: [],
        _FAM_BUILDINGS_TABLE: [],
        _ERRORS_TABLE: [],
    }
    with TemporaryDirectory(prefix=f"holocron-dxbi-bronze-{run_id}-") as scratch:
        scratch_path = Path(scratch)
        for file_name in jsonl_file_names:
            file_entry = files_by_name[file_name]
            report_slice = _slice_from_file_entry(file_entry)
            if report_slice is not None:
                report_slices.add(report_slice)
            local_path = download_manifest_file(
                file_name=file_name,
                file_entry=file_entry,
                s3=s3,
                scratch_path=scratch_path,
                source_label="DXBI",
            )
            for raw_row in read_jsonl_manifest_rows(
                path=local_path,
                file_entry=file_entry,
                source_label="DXBI",
            ):
                if raw_row.get("table") or raw_row.get("cells"):
                    row = _report_row_tuple(raw_row, fallback_run_id=run_id)
                    report_rows.append(row)
                    report_slices.add((row[6], row[7]))
                elif file_name == "dxbi_heatmap_rental_buildings.jsonl":
                    heatmap_rows_by_table[_RENTAL_BUILDINGS_TABLE].append(
                        _rental_building_row_tuple(raw_row, fallback_run_id=run_id)
                    )
                elif file_name in _HEATMAP_RESPONSE_FILES:
                    heatmap_rows_by_table[_HEATMAP_RESPONSE_FILES[file_name]].append(
                        _endpoint_response_row_tuple(raw_row, fallback_run_id=run_id)
                    )
                elif file_name == "dxbi_heatmap_errors.jsonl":
                    heatmap_rows_by_table[_ERRORS_TABLE].append(
                        _error_row_tuple(raw_row, fallback_run_id=run_id)
                    )

    ensure_schema(clickhouse=clickhouse)
    if report_slices:
        replace_where_rows(
            clickhouse=clickhouse,
            table=_TABLE_NAME,
            predicate=_slice_delete_predicate(report_slices),
            rows=report_rows,
            column_names=_TABLE_COLUMNS,
        )

    for table_name, rows in heatmap_rows_by_table.items():
        if not rows and table_name not in _present_heatmap_tables(files_by_name):
            continue
        clickhouse.replace_table_rows(
            table=table_name,
            rows=rows,
            column_names=_heatmap_columns(table_name),
            staging_suffix=run_id,
        )

    table_row_counts = {}
    if report_slices or report_rows:
        table_row_counts[_TABLE_NAME] = len(report_rows)
    table_row_counts.update(
        {table_name: len(rows) for table_name, rows in heatmap_rows_by_table.items() if rows}
    )
    return bronze_load_result(source=source_name, run_id=run_id, table_row_counts=table_row_counts)


def _slice_from_file_entry(file_entry: dict[str, Any]) -> tuple[date, date] | None:
    metadata = file_entry.get("metadata")
    if not isinstance(metadata, dict):
        return None
    start = string_value(metadata.get("slice_start_date"))
    end = string_value(metadata.get("slice_end_date"))
    if not start or not end:
        return None
    return (date.fromisoformat(start), date.fromisoformat(end))


def _present_heatmap_tables(files_by_name: dict[str, dict[str, Any]]) -> set[str]:
    tables: set[str] = set()
    if "dxbi_heatmap_rental_buildings.jsonl" in files_by_name:
        tables.add(_RENTAL_BUILDINGS_TABLE)
    if "dxbi_heatmap_errors.jsonl" in files_by_name:
        tables.add(_ERRORS_TABLE)
    for file_name, table_name in _HEATMAP_RESPONSE_FILES.items():
        if file_name in files_by_name:
            tables.add(table_name)
    return tables


def _heatmap_columns(table_name: str) -> tuple[str, ...]:
    if table_name == _RENTAL_BUILDINGS_TABLE:
        return _RENTAL_BUILDING_COLUMNS
    if table_name == _ERRORS_TABLE:
        return _ERROR_COLUMNS
    return _ENDPOINT_RESPONSE_COLUMNS


def _hash_key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()
