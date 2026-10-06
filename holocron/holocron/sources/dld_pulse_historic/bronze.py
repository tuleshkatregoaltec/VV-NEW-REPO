from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
import csv
from datetime import datetime
import hashlib
from io import TextIOWrapper
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any, cast

from holocron.contracts import (
    BronzeLoadResult,
    ClickHouseInserter,
    RawFileStore,
    RawManifest,
    RawManifestFile,
)
from holocron.platform.bronze import bronze_load_result, stable_json, validate_raw_manifest
from holocron.platform.clickhouse import quote_clickhouse_identifier, sql_string
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.manifests import manifest_s3_key
from holocron.platform.raw_files import (
    download_manifest_file,
    manifest_files_by_name,
    require_manifest_file,
    string_value,
    validate_manifest_row_count,
)

_SOURCE_NAME = "dld_pulse_historic"
_SOURCE_SYSTEM = "dubai_pulse"
_MODE = "historic_pulse"
_NULL_STRINGS = {"", "null", "none", "nan"}
_PULSE_DATE_FORMAT = "%d-%m-%Y"
_DEFAULT_DATETIME = datetime(1970, 1, 1)
_MIN_CLICKHOUSE_DATETIME = datetime(1970, 1, 1)
_MAX_SAFE_DATETIME = datetime(2100, 1, 1)
_DEFAULT_BATCH_SIZE = 5_000
_MAX_STREAMING_SIZE_BYTES = 512 * 1024 * 1024

_TRANSACTION_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "transaction_number",
    "instance_date",
    "group_id",
    "group_en",
    "group_ar",
    "procedure_id",
    "procedure_en",
    "procedure_ar",
    "procedure_area",
    "actual_area",
    "trans_value",
    "total_buyer",
    "total_seller",
    "property_id",
    "property_type_id",
    "prop_type_en",
    "prop_type_ar",
    "property_sub_type_id",
    "prop_sb_type_en",
    "prop_sb_type_ar",
    "usage_id",
    "usage_en",
    "usage_ar",
    "rooms_en",
    "rooms_ar",
    "parking",
    "building_age",
    "parcel_id",
    "area_id",
    "area_en",
    "area_ar",
    "project_en",
    "project_ar",
    "master_project_en",
    "master_project_ar",
    "is_free_hold",
    "is_free_hold_en",
    "is_free_hold_ar",
    "is_offplan",
    "is_offplan_en",
    "is_offplan_ar",
    "nearest_metro_en",
    "nearest_metro_ar",
    "nearest_mall_en",
    "nearest_mall_ar",
    "nearest_landmark_en",
    "nearest_landmark_ar",
    "source_system",
    "source_file",
    "source_row_index",
    "raw_json",
    "raw_manifest_s3_key",
    "project_number",
    "building_name_en",
    "building_name_ar",
    "reg_type_id",
    "reg_type_en",
    "reg_type_ar",
    "meter_sale_price",
    "rent_value",
    "meter_rent_price",
    "no_of_parties_role_1",
    "no_of_parties_role_2",
    "no_of_parties_role_3",
)

_RENT_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "contract_number",
    "registration_date",
    "start_date",
    "end_date",
    "property_id",
    "land_property_id",
    "ejari_property_type_id",
    "ejari_property_sub_type_id",
    "prop_type_en",
    "prop_type_ar",
    "prop_sub_type_en",
    "prop_sub_type_ar",
    "property_usage_id",
    "usage_en",
    "usage_ar",
    "rooms",
    "parking",
    "actual_area",
    "annual_amount",
    "contract_amount",
    "total_properties",
    "version_number",
    "version_en",
    "version_ar",
    "parcel_id",
    "area_id",
    "area_en",
    "area_ar",
    "project_en",
    "project_ar",
    "master_project_en",
    "master_project_ar",
    "is_free_hold",
    "is_free_hold_en",
    "is_free_hold_ar",
    "nearest_metro_en",
    "nearest_metro_ar",
    "nearest_mall_en",
    "nearest_mall_ar",
    "nearest_landmark_en",
    "nearest_landmark_ar",
    "source_system",
    "source_file",
    "source_row_index",
    "raw_json",
    "raw_manifest_s3_key",
    "line_number",
    "project_number",
    "tenant_type_id",
    "tenant_type_en",
    "tenant_type_ar",
    "contract_reg_type_id",
    "contract_reg_type_en",
    "contract_reg_type_ar",
    "ejari_bus_property_type_id",
    "ejari_bus_property_type_en",
    "ejari_bus_property_type_ar",
)

_UNIT_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "category",
    "endpoint",
    "raw_json",
    "source_system",
    "source_file",
    "source_row_index",
    "raw_manifest_s3_key",
    "property_id",
    "area_id",
    "zone_id",
    "area_en",
    "area_ar",
    "land_number",
    "land_sub_number",
    "building_number",
    "unit_number",
    "unit_balcony_area",
    "unit_parking_number",
    "parking_allocation_type",
    "parking_allocation_type_en",
    "parking_allocation_type_ar",
    "common_area",
    "actual_common_area",
    "floor",
    "rooms",
    "rooms_en",
    "rooms_ar",
    "actual_area",
    "property_type_id",
    "property_type_en",
    "property_type_ar",
    "property_sub_type_id",
    "prop_sub_type_en",
    "prop_sub_type_ar",
    "parent_property_id",
    "grandparent_property_id",
    "creation_date",
    "municipality_zip_code",
    "municipality_number",
    "parcel_id",
    "is_free_hold",
    "is_lease_hold",
    "is_registered",
    "pre_registration_number",
    "master_project_id",
    "master_project_en",
    "master_project_ar",
    "project_id",
    "project_en",
    "project_ar",
    "land_type_id",
    "land_type_en",
    "land_type_ar",
)

_BUILDING_COLUMNS = (
    "row_key",
    "run_id",
    "scraped_at",
    "mode",
    "date_window_start",
    "date_window_end",
    "page_index",
    "row_index",
    "building_number",
    "parent_property_id",
    "parcel_id",
    "creation_date",
    "land_number",
    "land_sub_number",
    "land_type_id",
    "land_type_en",
    "land_type_ar",
    "prop_sub_type_id",
    "prop_sub_type_en",
    "prop_sub_type_ar",
    "actual_area",
    "built_up_area",
    "common_area",
    "actual_common_area",
    "floors",
    "bld_levels",
    "flats",
    "rooms",
    "rooms_en",
    "rooms_ar",
    "offices",
    "shops",
    "car_parks",
    "elevators",
    "swimming_pools",
    "is_free_hold",
    "is_free_hold_en",
    "is_free_hold_ar",
    "is_lease_hold",
    "is_lease_hold_en",
    "is_lease_hold_ar",
    "is_offplan_en",
    "is_offplan_ar",
    "is_registered",
    "pre_registration_number",
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
    "source_system",
    "source_file",
    "source_row_index",
    "raw_json",
    "raw_manifest_s3_key",
    "property_id",
    "property_type_id",
    "property_type_en",
    "property_type_ar",
    "project_id",
)

_LAND_COLUMNS = (
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
    "source_system",
    "source_file",
    "source_row_index",
    "raw_json",
    "raw_manifest_s3_key",
    "property_id",
    "property_type_id",
    "property_type_en",
    "property_type_ar",
    "property_sub_type_id",
    "project_id",
)

_PROJECT_COLUMNS = (
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
    "source_system",
    "source_file",
    "source_row_index",
    "raw_json",
    "raw_manifest_s3_key",
    "project_id",
    "developer_id",
    "developer_name",
    "master_developer_id",
    "master_developer_number",
    "master_developer_name",
    "project_type_id",
    "project_classification_id",
    "project_classification_ar",
    "escrow_agent_id",
    "escrow_agent_name",
    "cancellation_date",
    "property_id",
    "area_id",
    "zoning_authority_id",
    "zoning_authority_en",
    "zoning_authority_ar",
)

_DEVELOPER_COLUMNS = (
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
    "source_system",
    "source_file",
    "source_row_index",
    "raw_json",
    "raw_manifest_s3_key",
    "developer_name_en",
    "developer_name_ar",
)


def load_release_to_clickhouse(
    *,
    raw_manifest: RawManifest,
    s3: RawFileStore,
    clickhouse: ClickHouseInserter,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    file_names: Sequence[str] = (),
    resume_existing_staging: bool = False,
    progress_log: Any = None,
) -> BronzeLoadResult:
    source, run_id = validate_raw_manifest(raw_manifest, expected_source=_SOURCE_NAME)
    files_by_name = manifest_files_by_name(raw_manifest)
    ensure_schema(clickhouse=clickhouse)

    load_specs = _selected_load_specs(
        requested_file_names=file_names,
        load_specs=(
            ("developers.csv", "dld_od_developers_bronze", _DEVELOPER_COLUMNS, _developer_row),
            ("projects.csv", "dld_od_projects_bronze", _PROJECT_COLUMNS, _project_row),
            ("lands.csv", "dld_od_lands_bronze", _LAND_COLUMNS, _land_row),
            ("buildings.csv", "dld_od_buildings_bronze", _BUILDING_COLUMNS, _building_row),
            ("units.csv", "dld_od_units_bronze", _UNIT_COLUMNS, _unit_row),
            (
                "transactions.csv",
                "dld_od_transactions_bronze",
                _TRANSACTION_COLUMNS,
                _transaction_row,
            ),
            ("rent_contracts.csv", "dld_od_rents_bronze", _RENT_COLUMNS, _rent_row),
        ),
    )
    table_counts: dict[str, int] = {}
    for file_name, table, columns, row_builder in load_specs:
        table_counts[table] = _load_csv_to_table(
            raw_manifest=raw_manifest,
            files_by_name=files_by_name,
            file_name=file_name,
            table=table,
            column_names=columns,
            row_builder=row_builder,
            run_id=run_id,
            s3=s3,
            clickhouse=clickhouse,
            batch_size=batch_size,
            resume_existing_staging=resume_existing_staging,
            progress_log=progress_log,
        )
    return bronze_load_result(source=source, run_id=run_id, table_row_counts=table_counts)


def _selected_load_specs(
    *,
    requested_file_names: Sequence[str],
    load_specs: Sequence[tuple[str, str, Sequence[str], Callable[..., tuple[Any, ...]]]],
) -> tuple[tuple[str, str, Sequence[str], Callable[..., tuple[Any, ...]]], ...]:
    requested = {Path(file_name).name for file_name in requested_file_names if file_name}
    if not requested:
        return tuple(load_specs)
    available = {file_name for file_name, _, _, _ in load_specs}
    unknown = requested - available
    if unknown:
        raise ValueError(f"Unknown Pulse historic file_names: {sorted(unknown)}")
    return tuple(spec for spec in load_specs if spec[0] in requested)


def _load_csv_to_table(
    *,
    raw_manifest: RawManifest,
    files_by_name: Mapping[str, RawManifestFile],
    file_name: str,
    table: str,
    column_names: Sequence[str],
    row_builder: Callable[..., tuple[Any, ...]],
    run_id: str,
    s3: RawFileStore,
    clickhouse: ClickHouseInserter,
    batch_size: int,
    resume_existing_staging: bool,
    progress_log: Any,
) -> int:
    file_entry = require_manifest_file(files_by_name, file_name)
    created_at = string_value(raw_manifest.get("created_at"))
    manifest_key = _raw_manifest_key(raw_manifest=raw_manifest, source=_SOURCE_NAME)
    staging_table = _staging_table_name(table=table, run_id=run_id, file_name=file_name)
    count = 0
    rows: list[tuple[Any, ...]] = []
    if resume_existing_staging and _table_exists(clickhouse=clickhouse, table=staging_table):
        count = _staged_source_row_count(
            clickhouse=clickhouse,
            table=staging_table,
            file_name=file_name,
        )
        if count > _int(file_entry.get("row_count")):
            raise ValueError(
                f"Existing staging table {staging_table} has {count} {file_name} rows, "
                f"more than manifest row_count {_int(file_entry.get('row_count'))}"
            )
        _log(
            progress_log,
            "resuming %s into %s from %s staged source rows",
            file_name,
            staging_table,
            count,
        )
    else:
        _prepare_staging_table(clickhouse=clickhouse, table=table, staging_table=staging_table)
    exchanged = False
    try:
        with _open_csv_reader(file_name=file_name, file_entry=file_entry, s3=s3) as reader:
            for row_index, csv_row in enumerate(reader, start=1):
                if row_index <= count:
                    continue
                count += 1
                rows.append(
                    row_builder(
                        csv_row,
                        run_id=run_id,
                        scraped_at=created_at,
                        row_index=row_index,
                        file_name=file_name,
                        manifest_key=manifest_key,
                    )
                )
                if len(rows) >= batch_size:
                    clickhouse.insert_rows(
                        table=staging_table,
                        rows=rows,
                        column_names=column_names,
                    )
                    _log(
                        progress_log,
                        "staged %s %s rows into %s",
                        len(rows),
                        file_name,
                        staging_table,
                    )
                    rows = []
        if rows:
            clickhouse.insert_rows(table=staging_table, rows=rows, column_names=column_names)
            _log(
                progress_log,
                "staged %s %s rows into %s",
                len(rows),
                file_name,
                staging_table,
            )
        validate_manifest_row_count(
            file_name=file_name,
            file_entry=file_entry,
            actual_row_count=count,
            source_label=_SOURCE_NAME,
        )
        _exchange_staging_table(
            clickhouse=clickhouse,
            table=table,
            staging_table=staging_table,
        )
        exchanged = True
    finally:
        if exchanged or not resume_existing_staging:
            _drop_table(clickhouse=clickhouse, table=staging_table)
    _log(progress_log, "loaded %s rows from %s into %s", count, file_name, table)
    return count


def _staging_table_name(*, table: str, run_id: str, file_name: str) -> str:
    digest = hashlib.sha1(
        f"{run_id}|{file_name}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]
    return f"{table}_staging_pulse_{digest}"


def _prepare_staging_table(
    *,
    clickhouse: ClickHouseInserter,
    table: str,
    staging_table: str,
) -> None:
    quoted_table = quote_clickhouse_identifier(table)
    quoted_staging = quote_clickhouse_identifier(staging_table)
    _drop_table(clickhouse=clickhouse, table=staging_table)
    clickhouse.command(f"CREATE TABLE {quoted_staging} AS {quoted_table}")
    clickhouse.command(
        f"INSERT INTO {quoted_staging} SELECT * FROM {quoted_table} "
        f"WHERE source_system != {sql_string(_SOURCE_SYSTEM)}"
    )


def _exchange_staging_table(
    *,
    clickhouse: ClickHouseInserter,
    table: str,
    staging_table: str,
) -> None:
    clickhouse.command(
        f"EXCHANGE TABLES {quote_clickhouse_identifier(table)} "
        f"AND {quote_clickhouse_identifier(staging_table)}"
    )


def _drop_table(*, clickhouse: ClickHouseInserter, table: str) -> None:
    clickhouse.command(f"DROP TABLE IF EXISTS {quote_clickhouse_identifier(table)}")


def _table_exists(*, clickhouse: ClickHouseInserter, table: str) -> bool:
    rows = (
        cast(Any, clickhouse)
        .query(
            "SELECT count() FROM system.tables "
            f"WHERE database = currentDatabase() AND name = {sql_string(table)}"
        )
        .result_rows
    )
    return bool(rows and rows[0][0])


def _staged_source_row_count(
    *,
    clickhouse: ClickHouseInserter,
    table: str,
    file_name: str,
) -> int:
    rows = (
        cast(Any, clickhouse)
        .query(
            f"SELECT count() FROM {quote_clickhouse_identifier(table)} "
            f"WHERE source_system = {sql_string(_SOURCE_SYSTEM)} "
            f"AND source_file = {sql_string(file_name)}"
        )
        .result_rows
    )
    return int(rows[0][0]) if rows else 0


@contextmanager
def _open_csv_reader(
    *,
    file_name: str,
    file_entry: Mapping[str, Any],
    s3: RawFileStore,
) -> Iterator[csv.DictReader]:
    s3_key = string_value(file_entry.get("s3_key"))
    client = getattr(s3, "_client", None)
    bucket = getattr(s3, "bucket", None)
    if client is not None and bucket and _should_stream_from_s3(file_entry):
        body = client.get_object(Bucket=bucket, Key=s3_key)["Body"]
        try:
            handle = TextIOWrapper(body, encoding="utf-8", newline="")
            yield csv.DictReader(handle)
        finally:
            body.close()
        return

    with TemporaryDirectory(
        prefix=f"holocron-{_SOURCE_NAME}-bronze-",
        dir=_scratch_parent(),
    ) as scratch:
        path = download_manifest_file(
            file_name=file_name,
            file_entry=dict(file_entry),
            s3=s3,
            scratch_path=Path(scratch),
            source_label=_SOURCE_NAME,
        )
        with path.open(encoding="utf-8", newline="") as handle:
            yield csv.DictReader(handle)


def _should_stream_from_s3(file_entry: Mapping[str, Any]) -> bool:
    size_bytes = _int(file_entry.get("size_bytes"))
    return 0 < size_bytes <= _MAX_STREAMING_SIZE_BYTES


def _scratch_parent() -> str:
    scratch_parent = Path(os.environ.get("HOLOCRON_SCRATCH_DIR") or Path.cwd() / "var" / "scratch")
    scratch_parent.mkdir(parents=True, exist_ok=True)
    return str(scratch_parent)


def _envelope(
    *,
    row_key: str,
    run_id: str,
    scraped_at: str,
    row_index: int,
) -> tuple[Any, ...]:
    return (
        row_key,
        run_id,
        scraped_at,
        _MODE,
        None,
        None,
        0,
        row_index,
    )


def _provenance(
    row: Mapping[str, Any],
    *,
    file_name: str,
    row_index: int,
    manifest_key: str,
) -> tuple[Any, ...]:
    payload = {_raw_json_key(key): _clean_raw_value(value) for key, value in row.items()}
    if manifest_key:
        payload["_manifest_s3_key"] = manifest_key
    return (
        _SOURCE_SYSTEM,
        file_name,
        row_index,
        stable_json(payload),
        manifest_key,
    )


def _transaction_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    scraped_at: str,
    row_index: int,
    file_name: str,
    manifest_key: str,
) -> tuple[Any, ...]:
    reg_type_en = _string(row.get("reg_type_en"))
    is_offplan = 1 if "off" in reg_type_en.lower() and "plan" in reg_type_en.lower() else 0
    return (
        *_envelope(
            row_key=_row_key(file_name, row_index, row.get("transaction_id")),
            run_id=run_id,
            scraped_at=scraped_at,
            row_index=row_index,
        ),
        _string(row.get("transaction_id")),
        _pulse_datetime_or_default(row.get("instance_date")),
        _int(row.get("trans_group_id")),
        _string(row.get("trans_group_en")),
        _string(row.get("trans_group_ar")),
        _int(row.get("procedure_id")),
        _string(row.get("procedure_name_en")),
        _string(row.get("procedure_name_ar")),
        _float(row.get("procedure_area")),
        0.0,
        _signed_int(row.get("actual_worth")),
        0,
        0,
        0,
        _int(row.get("property_type_id")),
        _string(row.get("property_type_en")),
        _string(row.get("property_type_ar")),
        _int(row.get("property_sub_type_id")),
        _string(row.get("property_sub_type_en")),
        _string(row.get("property_sub_type_ar")),
        0,
        _string(row.get("property_usage_en")),
        _string(row.get("property_usage_ar")),
        _string(row.get("rooms_en")),
        _string(row.get("rooms_ar")),
        _string(row.get("has_parking")),
        0,
        "",
        _int(row.get("area_id")),
        _string(row.get("area_name_en")),
        _string(row.get("area_name_ar")),
        _string(row.get("project_name_en")),
        _string(row.get("project_name_ar")),
        _string(row.get("master_project_en")),
        _string(row.get("master_project_ar")),
        0,
        "",
        "",
        is_offplan,
        "Off-Plan" if is_offplan else "",
        "",
        _string(row.get("nearest_metro_en")),
        _string(row.get("nearest_metro_ar")),
        _string(row.get("nearest_mall_en")),
        _string(row.get("nearest_mall_ar")),
        _string(row.get("nearest_landmark_en")),
        _string(row.get("nearest_landmark_ar")),
        *_provenance(row, file_name=file_name, row_index=row_index, manifest_key=manifest_key),
        _string(row.get("project_number")),
        _string(row.get("building_name_en")),
        _string(row.get("building_name_ar")),
        _int(row.get("reg_type_id")),
        reg_type_en,
        _string(row.get("reg_type_ar")),
        _float(row.get("meter_sale_price")),
        _float(row.get("rent_value")),
        _float(row.get("meter_rent_price")),
        _int(row.get("no_of_parties_role_1")),
        _int(row.get("no_of_parties_role_2")),
        _int(row.get("no_of_parties_role_3")),
    )


def _rent_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    scraped_at: str,
    row_index: int,
    file_name: str,
    manifest_key: str,
) -> tuple[Any, ...]:
    start_date = _pulse_datetime_or_default(row.get("contract_start_date"))
    return (
        *_envelope(
            row_key=_row_key(file_name, row_index, row.get("contract_id"), row.get("line_number")),
            run_id=run_id,
            scraped_at=scraped_at,
            row_index=row_index,
        ),
        _string(row.get("contract_id")),
        start_date,
        start_date,
        _pulse_datetime_or_default(row.get("contract_end_date")),
        0,
        0,
        _int(row.get("ejari_property_type_id")),
        _int(row.get("ejari_property_sub_type_id")),
        _string(row.get("ejari_property_type_en")),
        _string(row.get("ejari_property_type_ar")),
        _string(row.get("ejari_property_sub_type_en")),
        _string(row.get("ejari_property_sub_type_ar")),
        0,
        _string(row.get("property_usage_en")),
        _string(row.get("property_usage_ar")),
        "",
        "",
        _float(row.get("actual_area")),
        _signed_int(row.get("annual_amount")),
        _signed_int(row.get("contract_amount")),
        _int(row.get("no_of_prop")),
        _int(row.get("contract_reg_type_id")),
        _string(row.get("contract_reg_type_en")),
        _string(row.get("contract_reg_type_ar")),
        "",
        _int(row.get("area_id")),
        _string(row.get("area_name_en")),
        _string(row.get("area_name_ar")),
        _string(row.get("project_name_en")),
        _string(row.get("project_name_ar")),
        _string(row.get("master_project_en")),
        _string(row.get("master_project_ar")),
        _boolish(row.get("is_free_hold")),
        "",
        "",
        _string(row.get("nearest_metro_en")),
        _string(row.get("nearest_metro_ar")),
        _string(row.get("nearest_mall_en")),
        _string(row.get("nearest_mall_ar")),
        _string(row.get("nearest_landmark_en")),
        _string(row.get("nearest_landmark_ar")),
        *_provenance(row, file_name=file_name, row_index=row_index, manifest_key=manifest_key),
        _int(row.get("line_number")),
        _string(row.get("project_number")),
        _int(row.get("tenant_type_id")),
        _string(row.get("tenant_type_en")),
        _string(row.get("tenant_type_ar")),
        _int(row.get("contract_reg_type_id")),
        _string(row.get("contract_reg_type_en")),
        _string(row.get("contract_reg_type_ar")),
        _int(row.get("ejari_bus_property_type_id")),
        _string(row.get("ejari_bus_property_type_en")),
        _string(row.get("ejari_bus_property_type_ar")),
    )


def _unit_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    scraped_at: str,
    row_index: int,
    file_name: str,
    manifest_key: str,
) -> tuple[Any, ...]:
    source_system, source_file, source_row_index, raw_json, raw_manifest_s3_key = _provenance(
        row,
        file_name=file_name,
        row_index=row_index,
        manifest_key=manifest_key,
    )
    return (
        *_envelope(
            row_key=_row_key(file_name, row_index, row.get("property_id"), row.get("unit_number")),
            run_id=run_id,
            scraped_at=scraped_at,
            row_index=row_index,
        ),
        "units",
        "units",
        raw_json,
        source_system,
        source_file,
        source_row_index,
        raw_manifest_s3_key,
        _int(row.get("property_id")),
        _int(row.get("area_id")),
        _int(row.get("zone_id")),
        _string(row.get("area_name_en")),
        _string(row.get("area_name_ar")),
        _string(row.get("land_number")),
        _string(row.get("land_sub_number")),
        _string(row.get("building_number")),
        _string(row.get("unit_number")),
        _float(row.get("unit_balcony_area")),
        _string(row.get("unit_parking_number")),
        _string(row.get("parking_allocation_type")),
        _string(row.get("parking_allocation_type_en")),
        _string(row.get("parking_allocation_type_ar")),
        _float(row.get("common_area")),
        _float(row.get("actual_common_area")),
        _string(row.get("floor")),
        _string(row.get("rooms")),
        _string(row.get("rooms_en")),
        _string(row.get("rooms_ar")),
        _float(row.get("actual_area")),
        _int(row.get("property_type_id")),
        _string(row.get("property_type_en")),
        _string(row.get("property_type_ar")),
        _int(row.get("property_sub_type_id")),
        _string(row.get("property_sub_type_en")),
        _string(row.get("property_sub_type_ar")),
        _int(row.get("parent_property_id")),
        _int(row.get("grandparent_property_id")),
        _pulse_datetime_or_default(row.get("creation_date")),
        _string(row.get("munc_zip_code")),
        _string(row.get("munc_number")),
        _string(row.get("parcel_id")),
        _boolish(row.get("is_free_hold")),
        _boolish(row.get("is_lease_hold")),
        _boolish(row.get("is_registered")),
        _string(row.get("pre_registration_number")),
        _int(row.get("master_project_id")),
        _string(row.get("master_project_en")),
        _string(row.get("master_project_ar")),
        _int(row.get("project_id")),
        _string(row.get("project_name_en")),
        _string(row.get("project_name_ar")),
        _int(row.get("land_type_id")),
        _string(row.get("land_type_en")),
        _string(row.get("land_type_ar")),
    )


def _building_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    scraped_at: str,
    row_index: int,
    file_name: str,
    manifest_key: str,
) -> tuple[Any, ...]:
    return (
        *_envelope(
            row_key=_row_key(
                file_name,
                row_index,
                row.get("property_id"),
                row.get("building_number"),
            ),
            run_id=run_id,
            scraped_at=scraped_at,
            row_index=row_index,
        ),
        _string(row.get("building_number")),
        _int(row.get("parent_property_id")),
        _string(row.get("parcel_id")),
        _pulse_datetime_or_default(row.get("creation_date")),
        _string(row.get("land_number")),
        _int(row.get("land_sub_number")),
        _int(row.get("land_type_id")),
        _string(row.get("land_type_en")),
        _string(row.get("land_type_ar")),
        _int(row.get("property_sub_type_id")),
        _string(row.get("property_sub_type_en")),
        _string(row.get("property_sub_type_ar")),
        _float(row.get("actual_area")),
        _float(row.get("built_up_area")),
        _float(row.get("common_area")),
        _float(row.get("actual_common_area")),
        _int(row.get("floors")),
        _int(row.get("bld_levels")),
        _int(row.get("flats")),
        _int(row.get("rooms")),
        _string(row.get("rooms_en")),
        _string(row.get("rooms_ar")),
        _int(row.get("offices")),
        _int(row.get("shops")),
        _int(row.get("car_parks")),
        _int(row.get("elevators")),
        _int(row.get("swimming_pools")),
        _boolish(row.get("is_free_hold")),
        "",
        "",
        _boolish(row.get("is_lease_hold")),
        "",
        "",
        "",
        "",
        _boolish(row.get("is_registered")),
        _string(row.get("pre_registration_number")),
        _int(row.get("area_id")),
        _string(row.get("area_name_en")),
        _string(row.get("area_name_ar")),
        _int(row.get("zone_id")),
        "",
        "",
        _int(row.get("master_project_id")),
        _string(row.get("master_project_en")),
        _string(row.get("master_project_ar")),
        "",
        _string(row.get("project_name_en")),
        _string(row.get("project_name_ar")),
        *_provenance(row, file_name=file_name, row_index=row_index, manifest_key=manifest_key),
        _int(row.get("property_id")),
        _int(row.get("property_type_id")),
        _string(row.get("property_type_en")),
        _string(row.get("property_type_ar")),
        _int(row.get("project_id")),
    )


def _land_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    scraped_at: str,
    row_index: int,
    file_name: str,
    manifest_key: str,
) -> tuple[Any, ...]:
    return (
        *_envelope(
            row_key=_row_key(file_name, row_index, row.get("property_id"), row.get("parcel_id")),
            run_id=run_id,
            scraped_at=scraped_at,
            row_index=row_index,
        ),
        _string(row.get("land_number")),
        _string(row.get("land_sub_number")),
        _string(row.get("parcel_id")),
        _string(row.get("munc_number")),
        _string(row.get("munc_zip_code")),
        _int(row.get("land_type_id")),
        _string(row.get("land_type_en")),
        _string(row.get("land_type_ar")),
        _float(row.get("actual_area")),
        _boolish(row.get("is_free_hold")),
        "",
        "",
        "",
        "",
        _boolish(row.get("is_registered")),
        _string(row.get("property_sub_type_en")),
        _string(row.get("property_sub_type_ar")),
        _int(row.get("area_id")),
        _string(row.get("area_name_en")),
        _string(row.get("area_name_ar")),
        _int(row.get("zone_id")),
        "",
        "",
        _int(row.get("master_project_id")),
        _string(row.get("master_project_en")),
        _string(row.get("master_project_ar")),
        "",
        _string(row.get("project_name_en")),
        _string(row.get("project_name_ar")),
        _string(row.get("pre_registration_number")),
        _string(row.get("separated_from")),
        _string(row.get("separated_reference")),
        *_provenance(row, file_name=file_name, row_index=row_index, manifest_key=manifest_key),
        _int(row.get("property_id")),
        _int(row.get("property_type_id")),
        _string(row.get("property_type_en")),
        _string(row.get("property_type_ar")),
        _int(row.get("property_sub_type_id")),
        _int(row.get("project_id")),
    )


def _project_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    scraped_at: str,
    row_index: int,
    file_name: str,
    manifest_key: str,
) -> tuple[Any, ...]:
    return (
        *_envelope(
            row_key=_row_key(
                file_name, row_index, row.get("project_id"), row.get("project_number")
            ),
            run_id=run_id,
            scraped_at=scraped_at,
            row_index=row_index,
        ),
        _int(row.get("project_number")),
        "",
        _string(row.get("project_name")),
        _DEFAULT_DATETIME,
        _pulse_datetime_or_none(row.get("project_start_date")),
        _pulse_datetime_or_none(row.get("project_end_date")),
        _pulse_datetime_or_none(row.get("completion_date")),
        None,
        _string(row.get("project_status")),
        "",
        _string(row.get("project_type_ar")),
        _float(row.get("percent_completed")),
        0,
        "",
        _int(row.get("no_of_units"))
        + _int(row.get("no_of_buildings"))
        + _int(row.get("no_of_villas"))
        + _int(row.get("no_of_lands")),
        _int(row.get("no_of_units")),
        _int(row.get("no_of_buildings")),
        _int(row.get("no_of_villas")),
        _int(row.get("no_of_lands")),
        _int(row.get("developer_number")),
        "",
        _string(row.get("developer_name")),
        _string(row.get("area_name_en")),
        _string(row.get("area_name_ar")),
        _string(row.get("zoning_authority_en")),
        _string(row.get("zoning_authority_ar")),
        _string(row.get("master_project_en")),
        _string(row.get("master_project_ar")),
        _string(row.get("project_description_en")),
        _string(row.get("project_description_ar")),
        *_provenance(row, file_name=file_name, row_index=row_index, manifest_key=manifest_key),
        _int(row.get("project_id")),
        _int(row.get("developer_id")),
        _string(row.get("developer_name")),
        _int(row.get("master_developer_id")),
        _int(row.get("master_developer_number")),
        _string(row.get("master_developer_name")),
        _int(row.get("project_type_id")),
        _int(row.get("project_classification_id")),
        _string(row.get("project_classification_ar")),
        _int(row.get("escrow_agent_id")),
        _string(row.get("escrow_agent_name")),
        _pulse_datetime_or_none(row.get("cancellation_date")),
        _int(row.get("property_id")),
        _int(row.get("area_id")),
        _int(row.get("zoning_authority_id")),
        _string(row.get("zoning_authority_en")),
        _string(row.get("zoning_authority_ar")),
    )


def _developer_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    scraped_at: str,
    row_index: int,
    file_name: str,
    manifest_key: str,
) -> tuple[Any, ...]:
    developer_en = _string(row.get("developer_name_en"))
    developer_ar = _string(row.get("developer_name_ar"))
    return (
        *_envelope(
            row_key=_row_key(
                file_name,
                row_index,
                row.get("developer_id"),
                row.get("developer_number"),
            ),
            run_id=run_id,
            scraped_at=scraped_at,
            row_index=row_index,
        ),
        _int(row.get("developer_number")),
        _int(row.get("developer_id")),
        developer_en,
        developer_ar,
        _pulse_datetime_or_default(row.get("registration_date")),
        _string(row.get("license_number")),
        _pulse_datetime_or_default(row.get("license_issue_date")),
        _pulse_datetime_or_default(row.get("license_expiry_date")),
        _int(row.get("license_source_id")),
        _string(row.get("license_source_en")),
        _string(row.get("license_source_ar")),
        _int(row.get("license_type_id")),
        _string(row.get("license_type_en")),
        _string(row.get("license_type_ar")),
        _string(row.get("legal_status")),
        _string(row.get("legal_status_en")),
        _string(row.get("legal_status_ar")),
        _string(row.get("chamber_of_commerce_no")),
        _int(row.get("participant_id")),
        _string(row.get("phone")),
        _string(row.get("fax")),
        _string(row.get("webpage")),
        *_provenance(row, file_name=file_name, row_index=row_index, manifest_key=manifest_key),
        developer_en,
        developer_ar,
    )


def _row_key(file_name: str, row_index: int, *parts: Any) -> str:
    payload = "|".join(
        [_SOURCE_SYSTEM, file_name, str(row_index), *(_string(part) for part in parts)]
    )
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


def _raw_manifest_key(*, raw_manifest: RawManifest, source: str) -> str:
    explicit_key = string_value(raw_manifest.get("manifest_s3_key"))
    if explicit_key:
        return explicit_key
    return manifest_s3_key(source=source, run_id=string_value(raw_manifest.get("run_id")))


def _string(value: Any) -> str:
    parsed = string_value(value)
    parsed = parsed.replace("\x00", "")
    return "" if parsed.lower() in _NULL_STRINGS else parsed


def _int(value: Any) -> int:
    return max(0, _signed_int(value))


def _signed_int(value: Any) -> int:
    parsed = _string(value).replace(",", "")
    if not parsed:
        return 0
    try:
        return int(parsed)
    except ValueError:
        try:
            return int(float(parsed))
        except ValueError:
            return 0


def _float(value: Any) -> float:
    parsed = _string(value).replace(",", "")
    if not parsed:
        return 0.0
    try:
        return float(parsed)
    except ValueError:
        return 0.0


def _clean_raw_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_clean_raw_value(item) for item in value]
    if isinstance(value, dict):
        return {_raw_json_key(key): _clean_raw_value(item) for key, item in value.items()}
    return value


def _raw_json_key(key: Any) -> str:
    if key is None:
        return "_extra_fields"
    return str(key)


def _boolish(value: Any) -> int:
    parsed = _string(value).lower()
    return 0 if parsed in {"", "0", "false", "no", "n"} else 1


def _pulse_datetime_or_default(value: Any) -> datetime:
    parsed = _pulse_datetime_or_none(value)
    return parsed or _DEFAULT_DATETIME


def _pulse_datetime_or_none(value: Any) -> datetime | None:
    parsed = _string(value)
    if not parsed:
        return None
    try:
        dt = datetime.strptime(parsed, _PULSE_DATE_FORMAT)
    except ValueError:
        return None
    if dt < _MIN_CLICKHOUSE_DATETIME or dt >= _MAX_SAFE_DATETIME:
        return None
    return dt


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _log(progress_log: Any, message: str, *args: Any) -> None:
    if progress_log is not None:
        progress_log.info(message, *args)


_allow_large_csv_fields()
