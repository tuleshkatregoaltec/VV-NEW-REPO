from __future__ import annotations

from typing import Any

from holocron.platform.bronze import (
    coerce_int,
    iso_datetime_or_default,
)
from holocron.platform.raw_files import string_value
from holocron.sources.dld_open_data_bronze import (
    build_open_data_bronze_loader,
    dld_envelope_tuple,
    dld_row_key,
)

_SOURCE_NAME = "dld_od_brokers"
_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "broker_number",
    "broker_id",
    "broker_en",
    "broker_ar",
    "gender_type_id",
    "gender_en",
    "gender_ar",
    "license_start_date",
    "license_end_date",
    "real_estate_id",
    "real_estate_number",
    "real_estate_en",
    "real_estate_ar",
    "real_estate_broker_id",
    "phone",
    "fax",
    "webpage",
)


def _row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    row_key = dld_row_key(raw_row)
    d = raw_row.get("raw") or {}
    return (
        *dld_envelope_tuple(raw_row, row_key=row_key, fallback_run_id=fallback_run_id),
        coerce_int(d.get("BROKER_NUMBER")),
        coerce_int(d.get("BROKER_ID")),
        string_value(d.get("BROKER_EN")),
        string_value(d.get("BROKER_AR")),
        coerce_int(d.get("GENDER_TYPE_ID")),
        string_value(d.get("GENDER_EN")),
        string_value(d.get("GENDER_AR")),
        iso_datetime_or_default(d.get("LICENSE_START_DATE")),
        iso_datetime_or_default(d.get("LICENSE_END_DATE")),
        coerce_int(d.get("REAL_ESTATE_ID")),
        coerce_int(d.get("REAL_ESTATE_NUMBER")),
        string_value(d.get("REAL_ESTATE_EN")),
        string_value(d.get("REAL_ESTATE_AR")),
        coerce_int(d.get("REAL_ESTATE_BROKER_ID")),
        string_value(d.get("PHONE")),
        string_value(d.get("FAX")),
        string_value(d.get("WEBPAGE")),
    )


load_release_to_clickhouse = build_open_data_bronze_loader(
    source_name=_SOURCE_NAME,
    column_names=_COLUMNS,
    row_builder=_row_tuple,
)
