from __future__ import annotations

from typing import Any

from holocron.platform.bronze import (
    coerce_float,
    coerce_int,
    iso_datetime_or_default,
    iso_datetime_or_none,
)
from holocron.platform.raw_files import string_value
from holocron.sources.dld_open_data_bronze import (
    build_open_data_bronze_loader,
    dld_envelope_tuple,
    dld_row_key,
)

_SOURCE_NAME = "dld_od_projects"
_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "project_number",
    "project_en",
    "project_ar",
    "adoption_date",
    "start_date",
    "end_date",
    "completion_date",
    "inspection_date",
    "project_status",
    "prj_type_en",
    "prj_type_ar",
    "percent_completed",
    "project_value",
    "escrow_account_number",
    "cnt_total",
    "cnt_unit",
    "cnt_building",
    "cnt_villa",
    "cnt_land",
    "developer_number",
    "developer_en",
    "developer_ar",
    "area_en",
    "area_ar",
    "zone_en",
    "zone_ar",
    "master_project_en",
    "master_project_ar",
    "description_en",
    "description_ar",
)


def _row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    row_key = dld_row_key(raw_row)
    d = raw_row.get("raw") or {}
    return (
        *dld_envelope_tuple(raw_row, row_key=row_key, fallback_run_id=fallback_run_id),
        coerce_int(d.get("PROJECT_NUMBER")),
        string_value(d.get("PROJECT_EN")),
        string_value(d.get("PROJECT_AR")),
        iso_datetime_or_default(d.get("ADOPTION_DATE")),
        iso_datetime_or_none(d.get("START_DATE")),
        iso_datetime_or_none(d.get("END_DATE")),
        iso_datetime_or_none(d.get("COMPLETION_DATE")),
        iso_datetime_or_none(d.get("INSPECTION_DATE")),
        string_value(d.get("PROJECT_STATUS")),
        string_value(d.get("PRJ_TYPE_EN")),
        string_value(d.get("PRJ_TYPE_AR")),
        coerce_float(d.get("PERCENT_COMPLETED")),
        coerce_int(d.get("PROJECT_VALUE")),
        string_value(d.get("ESCROW_ACCOUNT_NUMBER")),
        coerce_int(d.get("CNT_TOTAL")),
        coerce_int(d.get("CNT_UNIT")),
        coerce_int(d.get("CNT_BUILDING")),
        coerce_int(d.get("CNT_VILLA")),
        coerce_int(d.get("CNT_LAND")),
        coerce_int(d.get("DEVELOPER_NUMBER")),
        string_value(d.get("DEVELOPER_EN")),
        string_value(d.get("DEVELOPER_AR")),
        string_value(d.get("AREA_EN")),
        string_value(d.get("AREA_AR")),
        string_value(d.get("ZONE_EN")),
        string_value(d.get("ZONE_AR")),
        string_value(d.get("MASTER_PROJECT_EN")),
        string_value(d.get("MASTER_PROJECT_AR")),
        string_value(d.get("DESCRIPTION_EN")),
        string_value(d.get("DESCRIPTION_AR")),
    )


load_release_to_clickhouse = build_open_data_bronze_loader(
    source_name=_SOURCE_NAME,
    column_names=_COLUMNS,
    row_builder=_row_tuple,
)
