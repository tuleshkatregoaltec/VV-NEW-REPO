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

_SOURCE_NAME = "dld_od_developers"
_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "developer_number",
    "developer_id",
    "developer_en",
    "developer_ar",
    "registration_date",
    "license_number",
    "license_issue_date",
    "license_expiry_date",
    "license_source_id",
    "license_source_en",
    "license_source_ar",
    "license_type_id",
    "license_type_en",
    "license_type_ar",
    "legal_status",
    "legal_status_en",
    "legal_status_ar",
    "chamber_of_commerce_no",
    "participant_id",
    "phone",
    "fax",
    "webpage",
)


def _row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    row_key = dld_row_key(raw_row)
    d = raw_row.get("raw") or {}
    return (
        *dld_envelope_tuple(raw_row, row_key=row_key, fallback_run_id=fallback_run_id),
        coerce_int(d.get("DEVELOPER_NUMBER")),
        coerce_int(d.get("DEVELOPER_ID")),
        string_value(d.get("DEVELOPER_EN")),
        string_value(d.get("DEVELOPER_AR")),
        iso_datetime_or_default(d.get("REGISTRATION_DATE")),
        string_value(d.get("LICENSE_NUMBER")),
        iso_datetime_or_default(d.get("LICENSE_ISSUE_DATE")),
        iso_datetime_or_default(d.get("LICENSE_EXPIRY_DATE")),
        coerce_int(d.get("LICENSE_SOURCE_ID")),
        string_value(d.get("LICENSE_SOURCE_EN")),
        string_value(d.get("LICENSE_SOURCE_AR")),
        coerce_int(d.get("LICENSE_TYPE_ID")),
        string_value(d.get("LICENSE_TYPE_EN")),
        string_value(d.get("LICENSE_TYPE_AR")),
        string_value(d.get("LEGAL_STATUS")),
        string_value(d.get("LEGAL_STATUS_EN")),
        string_value(d.get("LEGAL_STATUS_AR")),
        string_value(d.get("CHAMBER_OF_COMMERCE_NO")),
        coerce_int(d.get("PARTICIPANT_ID")),
        string_value(d.get("PHONE")),
        string_value(d.get("FAX")),
        string_value(d.get("WEBPAGE")),
    )


load_release_to_clickhouse = build_open_data_bronze_loader(
    source_name=_SOURCE_NAME,
    column_names=_COLUMNS,
    row_builder=_row_tuple,
)
