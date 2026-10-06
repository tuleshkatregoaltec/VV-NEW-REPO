from __future__ import annotations

from typing import Any

from holocron.contracts import BronzeLoadResult, ClickHouseReplacer, RawFileStore, RawManifest
from holocron.platform.bronze import (
    bronze_load_result,
    coerce_boolish_uint8,
    coerce_float_or_none,
    coerce_int,
    load_jsonl_table_rows,
    stable_json,
    validate_raw_manifest,
)
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.raw_files import manifest_files_by_name, string_value
from holocron.sources.pf_locations.source import PF_LOCATIONS_SOURCE_NAME

_TABLE_NAME = "pf_locations_bronze"
_FILE_NAME = "pf_locations.jsonl"
_TABLE_COLUMNS = (
    "location_id",
    "parent_location_id",
    "scraped_at",
    "locale",
    "path",
    "path_ids_json",
    "path_name",
    "name",
    "level",
    "location_type",
    "url_slug",
    "url_city_slug",
    "lat",
    "lng",
    "children_count",
    "top_location_id",
    "published",
    "is_dubai",
    "raw_json",
    "run_id",
)


def load_release_to_clickhouse(
    *,
    raw_manifest: RawManifest,
    s3: RawFileStore,
    clickhouse: ClickHouseReplacer,
) -> BronzeLoadResult:
    source_name, run_id = validate_raw_manifest(
        raw_manifest,
        expected_source=PF_LOCATIONS_SOURCE_NAME,
    )
    files_by_name = manifest_files_by_name(raw_manifest)
    table_rows = load_jsonl_table_rows(
        files_by_name=files_by_name,
        file_name=_FILE_NAME,
        s3=s3,
        run_id=run_id,
        source_label="Property Finder locations",
        row_builder=_row_tuple,
        required=True,
        scratch_prefix="holocron-pf-locations-bronze",
    )

    ensure_schema(clickhouse=clickhouse)
    row_count = clickhouse.replace_table_rows(
        table=_TABLE_NAME,
        rows=table_rows,
        column_names=_TABLE_COLUMNS,
        staging_suffix=run_id,
    )
    table_row_counts = {_TABLE_NAME: row_count}
    return bronze_load_result(source=source_name, run_id=run_id, table_row_counts=table_row_counts)


def _row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    coordinates = raw_row.get("coordinates")
    if not isinstance(coordinates, dict):
        coordinates = {}
    return (
        string_value(raw_row.get("location_id")),
        _nullable_string(raw_row.get("parent_location_id")),
        string_value(raw_row.get("scraped_at")),
        string_value(raw_row.get("locale")),
        string_value(raw_row.get("path")),
        _json(raw_row.get("path_ids") or []),
        string_value(raw_row.get("path_name")),
        string_value(raw_row.get("name")),
        coerce_int(raw_row.get("level")),
        string_value(raw_row.get("location_type")),
        string_value(raw_row.get("url_slug")),
        string_value(raw_row.get("url_city_slug")),
        coerce_float_or_none(_first_value(coordinates, "lat", "latitude")),
        coerce_float_or_none(_first_value(coordinates, "lon", "lng", "longitude")),
        max(coerce_int(raw_row.get("children_count")), 0),
        string_value(raw_row.get("top_location_id")),
        coerce_boolish_uint8(raw_row.get("published")),
        coerce_boolish_uint8(raw_row.get("is_dubai")),
        _json(raw_row.get("raw") or raw_row),
        string_value(raw_row.get("_run_id")) or fallback_run_id,
    )


def _first_value(container: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in container:
            return container[key]
    return None


def _nullable_string(value: Any) -> str | None:
    parsed = string_value(value)
    return parsed or None


def _json(value: Any) -> str:
    return stable_json(value)
