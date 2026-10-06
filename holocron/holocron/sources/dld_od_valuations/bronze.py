from __future__ import annotations

from typing import Any

from holocron.platform.bronze import (
    coerce_float,
    coerce_int,
    iso_datetime_or_default,
)
from holocron.platform.raw_files import string_value
from holocron.sources.dld_open_data_bronze import (
    build_open_data_bronze_loader,
    dld_envelope_tuple,
    dld_row_key,
)

_SOURCE_NAME = "dld_od_valuations"
_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "procedure_number",
    "procedure_year",
    "instance_date",
    "property_id",
    "property_type_id",
    "property_type_en",
    "property_type_ar",
    "property_sub_type_id",
    "prop_sub_type_en",
    "prop_sub_type_ar",
    "actual_area",
    "procedure_area",
    "actual_worth",
    "property_total_value",
    "row_status_code",
    "area_id",
    "area_en",
    "area_ar",
)


def _row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    row_key = dld_row_key(raw_row)
    d = raw_row.get("raw") or {}
    return (
        *dld_envelope_tuple(raw_row, row_key=row_key, fallback_run_id=fallback_run_id),
        coerce_int(d.get("PROCEDURE_NUMBER")),
        coerce_int(d.get("PROCEDURE_YEAR")),
        iso_datetime_or_default(d.get("INSTANCE_DATE")),
        coerce_int(d.get("PROPERTY_ID")),
        coerce_int(d.get("PROPERTY_TYPE_ID")),
        string_value(d.get("PROPERTY_TYPE_EN")),
        string_value(d.get("PROPERTY_TYPE_AR")),
        coerce_int(d.get("PROPERTY_SUB_TYPE_ID")),
        string_value(d.get("PROP_SUB_TYPE_EN")),
        string_value(d.get("PROP_SUB_TYPE_AR")),
        coerce_float(d.get("ACTUAL_AREA")),
        coerce_float(d.get("PROCEDURE_AREA")),
        coerce_int(d.get("ACTUAL_WORTH")),
        coerce_int(d.get("PROPERTY_TOTAL_VALUE")),
        string_value(d.get("ROW_STATUS_CODE")),
        coerce_int(d.get("AREA_ID")),
        string_value(d.get("AREA_EN")),
        string_value(d.get("AREA_AR")),
    )


load_release_to_clickhouse = build_open_data_bronze_loader(
    source_name=_SOURCE_NAME,
    column_names=_COLUMNS,
    row_builder=_row_tuple,
)
