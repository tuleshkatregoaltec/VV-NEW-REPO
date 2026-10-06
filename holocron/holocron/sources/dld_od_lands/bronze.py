from __future__ import annotations

from typing import Any

from holocron.platform.bronze import (
    coerce_boolish_uint8,
    coerce_float,
    coerce_int,
)
from holocron.platform.raw_files import string_value
from holocron.sources.dld_open_data_bronze import (
    build_open_data_bronze_loader,
    dld_envelope_tuple,
    dld_row_key,
)

_SOURCE_NAME = "dld_od_lands"
_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "land_number",
    "land_sub_number",
    "parcel_id",
    "municipality_number",
    "dm_zip_code",
    "land_type_id",
    "land_type_en",
    "land_type_ar",
    "actual_area",
    "is_free_hold",
    "is_free_hold_en",
    "is_free_hold_ar",
    "is_offplan_en",
    "is_offplan_ar",
    "is_registered",
    "prop_sub_type_en",
    "prop_sub_type_ar",
    "area_id",
    "area_en",
    "area_ar",
    "zone_id",
    "zone_en",
    "zone_ar",
    "master_project_id",
    "master_project_en",
    "master_project_ar",
    "project_number",
    "project_en",
    "project_ar",
    "pre_registration_number",
    "separated_from",
    "separated_reference",
)


def _row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    row_key = dld_row_key(raw_row)
    d = raw_row.get("raw") or {}
    return (
        *dld_envelope_tuple(raw_row, row_key=row_key, fallback_run_id=fallback_run_id),
        string_value(d.get("LAND_NUMBER")),
        string_value(d.get("LAND_SUB_NUMBER")),
        string_value(d.get("PARCEL_ID")),
        string_value(d.get("MUNICIPALITY_NUMBER")),
        string_value(d.get("DM_ZIP_CODE")),
        coerce_int(d.get("LAND_TYPE_ID")),
        string_value(d.get("LAND_TYPE_EN")),
        string_value(d.get("LAND_TYPE_AR")),
        coerce_float(d.get("ACTUAL_AREA")),
        coerce_boolish_uint8(d.get("IS_FREE_HOLD")),
        string_value(d.get("IS_FREE_HOLD_EN")),
        string_value(d.get("IS_FREE_HOLD_AR")),
        string_value(d.get("IS_OFFPLAN_EN")),
        string_value(d.get("IS_OFFPLAN_AR")),
        coerce_boolish_uint8(d.get("IS_REGISTERED")),
        string_value(d.get("PROP_SUB_TYPE_EN")),
        string_value(d.get("PROP_SUB_TYPE_AR")),
        coerce_int(d.get("AREA_ID")),
        string_value(d.get("AREA_EN")),
        string_value(d.get("AREA_AR")),
        coerce_int(d.get("ZONE_ID")),
        string_value(d.get("ZONE_EN")),
        string_value(d.get("ZONE_AR")),
        coerce_int(d.get("MASTER_PROJECT_ID")),
        string_value(d.get("MASTER_PROJECT_EN")),
        string_value(d.get("MASTER_PROJECT_AR")),
        string_value(d.get("PROJECT_NUMBER")),
        string_value(d.get("PROJECT_EN")),
        string_value(d.get("PROJECT_AR")),
        string_value(d.get("PRE_REGISTRATION_NUMBER")),
        string_value(d.get("SEPARATED_FROM")),
        string_value(d.get("SEPARATED_REFERENCE")),
    )


load_release_to_clickhouse = build_open_data_bronze_loader(
    source_name=_SOURCE_NAME,
    column_names=_COLUMNS,
    row_builder=_row_tuple,
)
