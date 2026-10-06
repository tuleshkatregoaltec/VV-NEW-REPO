from __future__ import annotations

import hashlib
from typing import Any

from holocron.contracts import (
    BronzeLoadResult,
    ClickHouseInserter,
    RawFileStore,
    RawManifest,
)
from holocron.platform.bronze import (
    bronze_load_result,
    coerce_boolish_uint8,
    coerce_float_or_none,
    coerce_int,
    coerce_nullable_int,
    load_jsonl_table_rows,
    replace_keyed_rows,
    stable_json,
    validate_raw_manifest,
)
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.raw_files import manifest_files_by_name, string_value
from holocron.sources.pf_listings.source import PF_LISTINGS_SOURCE_NAME

_LISTINGS_TABLE = "pf_listings_bronze"
_DETAILS_TABLE = "pf_listing_details_bronze"
_PROPERTIES_FILE = "pf_listing_properties.jsonl"
_DETAILS_FILE = "pf_listing_details.jsonl"
_LISTING_COLUMNS = (
    "property_key",
    "run_id",
    "scraped_at",
    "query_signature",
    "category_id",
    "location_id",
    "property_type_id",
    "bedroom",
    "min_price",
    "max_price",
    "page",
    "wrapper_index",
    "listing_id",
    "property_id",
    "reference",
    "details_path",
    "share_url",
    "title",
    "property_type_json",
    "price_json",
    "size_json",
    "bedrooms",
    "bathrooms",
    "listing_location_ids_json",
    "listing_location_names_json",
    "city_location_id",
    "community_location_id",
    "subcommunity_location_id",
    "building_location_id",
    "leaf_location_id",
    "lat",
    "lng",
    "is_available",
    "is_verified",
    "is_featured",
    "is_premium",
    "delta_reason",
    "selected_for_detail",
    "property_fingerprint",
    "agent_json",
    "broker_json",
    "client_json",
    "images_json",
    "raw_property_json",
    "raw_wrapper_json",
)
_DETAIL_COLUMNS = (
    "detail_key",
    "run_id",
    "scraped_at",
    "listing_id",
    "property_id",
    "property_key",
    "details_path",
    "category_id",
    "location_id",
    "status",
    "error",
    "detail_property_json",
    "raw_json",
)


def load_release_to_clickhouse(
    *,
    raw_manifest: RawManifest,
    s3: RawFileStore,
    clickhouse: ClickHouseInserter,
) -> BronzeLoadResult:
    source_name, run_id = validate_raw_manifest(
        raw_manifest,
        expected_source=PF_LISTINGS_SOURCE_NAME,
    )
    files_by_name = manifest_files_by_name(raw_manifest)
    listing_rows = load_jsonl_table_rows(
        files_by_name=files_by_name,
        file_name=_PROPERTIES_FILE,
        s3=s3,
        run_id=run_id,
        source_label="Property Finder listings",
        row_builder=_listing_row_tuple,
        scratch_prefix="holocron-pf-listings-bronze",
    )
    detail_rows = load_jsonl_table_rows(
        files_by_name=files_by_name,
        file_name=_DETAILS_FILE,
        s3=s3,
        run_id=run_id,
        source_label="Property Finder listing details",
        row_builder=_detail_row_tuple,
        scratch_prefix="holocron-pf-listings-bronze",
    )

    ensure_schema(clickhouse=clickhouse)
    table_row_counts = {
        _LISTINGS_TABLE: len(listing_rows),
        _DETAILS_TABLE: len(detail_rows),
    }
    replace_keyed_rows(
        clickhouse=clickhouse,
        table=_LISTINGS_TABLE,
        key_column="property_key",
        key_values=[row[0] for row in listing_rows],
        rows=listing_rows,
        column_names=_LISTING_COLUMNS,
    )
    replace_keyed_rows(
        clickhouse=clickhouse,
        table=_DETAILS_TABLE,
        key_column="property_key",
        key_values=[row[5] for row in detail_rows],
        rows=detail_rows,
        column_names=_DETAIL_COLUMNS,
    )
    return bronze_load_result(source=source_name, run_id=run_id, table_row_counts=table_row_counts)


def _listing_row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    return (
        string_value(raw_row.get("property_key")),
        string_value(raw_row.get("_run_id")) or fallback_run_id,
        string_value(raw_row.get("scraped_at")),
        string_value(raw_row.get("query_signature")),
        max(coerce_int(raw_row.get("category_id")), 0),
        string_value(raw_row.get("location_id")),
        coerce_nullable_int(raw_row.get("property_type_id")),
        coerce_nullable_int(raw_row.get("bedroom")),
        coerce_nullable_int(raw_row.get("min_price")),
        coerce_nullable_int(raw_row.get("max_price")),
        max(coerce_int(raw_row.get("page")), 0),
        max(coerce_int(raw_row.get("wrapper_index")), 0),
        string_value(raw_row.get("listing_id")),
        string_value(raw_row.get("property_id")),
        string_value(raw_row.get("reference")),
        string_value(raw_row.get("details_path")),
        string_value(raw_row.get("share_url")),
        string_value(raw_row.get("title")),
        _json(raw_row.get("type")),
        _json(raw_row.get("price")),
        _json(raw_row.get("size")),
        string_value(raw_row.get("bedrooms")),
        string_value(raw_row.get("bathrooms")),
        _json(raw_row.get("listing_location_ids") or []),
        _json(raw_row.get("listing_location_names") or []),
        string_value(raw_row.get("city_location_id")),
        string_value(raw_row.get("community_location_id")),
        string_value(raw_row.get("subcommunity_location_id")),
        string_value(raw_row.get("building_location_id")),
        string_value(raw_row.get("leaf_location_id")),
        coerce_float_or_none(raw_row.get("latitude")),
        coerce_float_or_none(raw_row.get("longitude")),
        coerce_boolish_uint8(raw_row.get("is_available")),
        coerce_boolish_uint8(raw_row.get("is_verified")),
        coerce_boolish_uint8(raw_row.get("is_featured")),
        coerce_boolish_uint8(raw_row.get("is_premium")),
        string_value(raw_row.get("delta_reason")),
        coerce_boolish_uint8(raw_row.get("selected_for_detail")),
        string_value(raw_row.get("property_fingerprint")),
        _json(raw_row.get("agent")),
        _json(raw_row.get("broker")),
        _json(raw_row.get("client")),
        _json(raw_row.get("images")),
        _json(raw_row.get("raw_property")),
        _json(raw_row.get("raw_wrapper")),
    )


def _detail_row_tuple(raw_row: dict[str, Any], *, fallback_run_id: str) -> tuple:
    property_key = string_value(raw_row.get("property_key"))
    details_path = string_value(raw_row.get("details_path"))
    detail_key = hashlib.sha1(
        f"{property_key}|{details_path}".encode(),
        usedforsecurity=False,
    ).hexdigest()
    detail_json = _json(raw_row.get("raw"))
    return (
        detail_key,
        string_value(raw_row.get("_run_id")) or fallback_run_id,
        string_value(raw_row.get("scraped_at")),
        string_value(raw_row.get("listing_id")),
        string_value(raw_row.get("property_id")),
        property_key,
        details_path,
        max(coerce_int(raw_row.get("category_id")), 0),
        string_value(raw_row.get("location_id")),
        string_value(raw_row.get("status")),
        string_value(raw_row.get("error")),
        _json(raw_row.get("detail_property")),
        detail_json,
    )


def _json(value: Any) -> str:
    return stable_json(value)
