"""Property Finder listings backed by ph_box ClickHouse bronze data."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.clickhouse.client import query
from app.listings.models import (
    ListingAnalyticsResponse,
    ListingAssetClass,
    ListingCardResponse,
    ListingDetailResponse,
    ListingFiltersResponse,
    ListingFloorPlanResponse,
    ListingImageResponse,
    ListingListResponse,
    ListingMarketPosition,
    ListingMode,
    ListingPartyResponse,
    ListingTrendPoint,
)

SALE_CATEGORY_IDS = (1, 3)
RENT_CATEGORY_IDS = (2, 4)
LISTINGS_TABLE = "pf_listings_bronze"
LISTINGS_SOURCE_LABEL = f"ph_box ClickHouse {LISTINGS_TABLE}"
PRICE_VALUE_EXPR = "JSONExtractInt(price_json, 'value')"
PRICE_PERIOD_EXPR = "lower(JSON_VALUE(price_json, '$.period'))"
SIZE_VALUE_EXPR = "JSONExtractFloat(size_json, 'value')"
PROPERTY_TYPE_EXPR = "JSON_VALUE(raw_property_json, '$.property_type')"
AREA_NAME_EXPR = "JSONExtract(listing_location_names_json, 'Array(String)')[2]"
PEER_LOCATION_EXPR = (
    "arrayElement(JSONExtract(listing_location_names_json, 'Array(String)'), -1)"
)
LISTED_AT_EXPR = "parseDateTimeBestEffortOrNull(JSON_VALUE(raw_property_json, '$.listed_date'))"
SCRAPED_AT_EXPR = "parseDateTimeBestEffortOrNull(scraped_at)"
MONTHLY_PRICE_EXPR = f"""
multiIf(
    {PRICE_PERIOD_EXPR} IN ('year', 'yearly', 'annual', 'annually'), {PRICE_VALUE_EXPR} / 12,
    {PRICE_PERIOD_EXPR} IN ('week', 'weekly'), {PRICE_VALUE_EXPR} * 52 / 12,
    {PRICE_PERIOD_EXPR} IN ('day', 'daily'), {PRICE_VALUE_EXPR} * 365 / 12,
    {PRICE_VALUE_EXPR}
)
"""
ANNUAL_PRICE_EXPR = f"""
multiIf(
    {PRICE_PERIOD_EXPR} IN ('month', 'monthly'), {PRICE_VALUE_EXPR} * 12,
    {PRICE_PERIOD_EXPR} IN ('week', 'weekly'), {PRICE_VALUE_EXPR} * 52,
    {PRICE_PERIOD_EXPR} IN ('day', 'daily'), {PRICE_VALUE_EXPR} * 365,
    {PRICE_VALUE_EXPR}
)
"""

NON_BUILDING_PROPERTY_TYPES = {
    "bungalow",
    "compound",
    "factory",
    "farm",
    "land",
    "labor camp",
    "staff accommodation",
    "townhouse",
    "villa",
    "warehouse",
}
MIN_BENCHMARK_COMPARABLES = 5
MARKET_POSITION_THRESHOLD = 0.10

SIZE_BUCKET_EXPR = f"""
toUInt32(round(
    {SIZE_VALUE_EXPR} / multiIf(
        lowerUTF8({PROPERTY_TYPE_EXPR}) IN ('apartment', 'office', 'shop'), 50,
        lowerUTF8({PROPERTY_TYPE_EXPR}) IN ('villa', 'townhouse'), 250,
        500
    )
) * multiIf(
    lowerUTF8({PROPERTY_TYPE_EXPR}) IN ('apartment', 'office', 'shop'), 50,
    lowerUTF8({PROPERTY_TYPE_EXPR}) IN ('villa', 'townhouse'), 250,
    500
))
"""
VALID_BENCHMARK_SIZE_EXPR = f"""
multiIf(
    lowerUTF8({PROPERTY_TYPE_EXPR}) = 'apartment' AND lowerUTF8(bedrooms) = 'studio',
        {SIZE_VALUE_EXPR} BETWEEN 150 AND 1500,
    lowerUTF8({PROPERTY_TYPE_EXPR}) = 'apartment' AND toInt32OrNull(bedrooms) = 1,
        {SIZE_VALUE_EXPR} BETWEEN 250 AND 3500,
    lowerUTF8({PROPERTY_TYPE_EXPR}) = 'apartment' AND toInt32OrNull(bedrooms) = 2,
        {SIZE_VALUE_EXPR} BETWEEN 350 AND 6000,
    lowerUTF8({PROPERTY_TYPE_EXPR}) = 'apartment' AND toInt32OrNull(bedrooms) = 3,
        {SIZE_VALUE_EXPR} BETWEEN 500 AND 10000,
    lowerUTF8({PROPERTY_TYPE_EXPR}) = 'apartment',
        {SIZE_VALUE_EXPR} BETWEEN 500 AND 20000,
    lowerUTF8({PROPERTY_TYPE_EXPR}) IN ('villa', 'townhouse'),
        {SIZE_VALUE_EXPR} BETWEEN 500 AND 50000,
    lowerUTF8({PROPERTY_TYPE_EXPR}) IN ('office', 'shop'),
        {SIZE_VALUE_EXPR} BETWEEN 100 AND 100000,
    {SIZE_VALUE_EXPR} BETWEEN 100 AND 250000
)
"""

EXPLICIT_URGENCY_TERMS = (
    "distress",
    "motivated seller",
    "urgent sale",
    "must sell",
    "price reduced",
    "reduced price",
    "priced to sell",
    "quick sale",
)
VALUE_LANGUAGE_TERMS = (
    "below market",
    "lowest price",
    "best price",
)

ACHIEVED_SALE_TYPES = {
    "residential": ["Apartment", "Villa"],
    "commercial": ["Office", "Shop", "Warehouse", "Workshop", "Clinic", "Show Rooms"],
}


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


def _json(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _as_list(value: Any) -> list[Any]:
    parsed = _json(value)
    return parsed if isinstance(parsed, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    parsed = _json(value)
    return parsed if isinstance(parsed, dict) else {}


def _listing_mode(category_id: int | None) -> ListingMode:
    return "rent" if category_id in RENT_CATEGORY_IDS else "sale"


def _asset_class(category_id: int | None) -> ListingAssetClass:
    return "commercial" if category_id in (3, 4) else "residential"


def _category_ids(
    mode: ListingMode, asset_class: ListingAssetClass | None = None
) -> tuple[int, ...]:
    if asset_class == "residential":
        return (2,) if mode == "rent" else (1,)
    if asset_class == "commercial":
        return (4,) if mode == "rent" else (3,)
    return RENT_CATEGORY_IDS if mode == "rent" else SALE_CATEGORY_IDS


def _price_expr(price_basis: str) -> str:
    if price_basis == "monthly":
        return MONTHLY_PRICE_EXPR
    if price_basis == "annual":
        return ANNUAL_PRICE_EXPR
    return PRICE_VALUE_EXPR


def _price_basis(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"annual", "monthly"} else "raw"


def _market_price_expr(mode: ListingMode) -> str:
    return ANNUAL_PRICE_EXPR if mode == "rent" else PRICE_VALUE_EXPR


def _location_hierarchy(
    names: list[str], property_type: str | None
) -> tuple[str | None, str | None, str | None]:
    """Normalize variable-depth source locations into area, project, and building.

    The source path always starts with city and community. Apartment and office paths
    end in a building, while landed and industrial asset paths end in a project/phase.
    """
    area = names[1] if len(names) > 1 else None
    tail = names[2:]
    if not tail:
        return area, None, None

    normalized_type = str(property_type or "").strip().lower()
    if normalized_type in NON_BUILDING_PROPERTY_TYPES:
        return area, tail[-1], None

    building = tail[-1]
    project = tail[-2] if len(tail) > 1 else None
    return area, project, building


def _market_position(delta_pct: float | None, comparable_count: int) -> ListingMarketPosition:
    if delta_pct is None or comparable_count < MIN_BENCHMARK_COMPARABLES:
        return "insufficient_data"
    if delta_pct < -MARKET_POSITION_THRESHOLD:
        return "below_market"
    if delta_pct > MARKET_POSITION_THRESHOLD:
        return "above_market"
    return "near_market"


def _benchmark_level(property_type: str | None, comparable_count: int) -> str:
    if comparable_count < MIN_BENCHMARK_COMPARABLES:
        return "insufficient_data"
    normalized_type = str(property_type or "").strip().lower()
    return "project_layout" if normalized_type in NON_BUILDING_PROPERTY_TYPES else "building_layout"


def _urgency_terms(
    mode: ListingMode, title: str | None, description: str | None
) -> tuple[str, list[str]]:
    if mode != "sale":
        return "none", []
    copy = f"{title or ''} {description or ''}".casefold()
    explicit = [term for term in EXPLICIT_URGENCY_TERMS if term in copy]
    if explicit:
        return "explicit_urgency", explicit
    supporting = [term for term in VALUE_LANGUAGE_TERMS if term in copy]
    if supporting:
        return "value_language", supporting
    return "none", []


def _price_period(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _listing_sql(sql: str) -> str:
    return sql.replace("{LISTINGS_TABLE}", LISTINGS_TABLE).replace(
        "{PRICE_VALUE_EXPR}", PRICE_VALUE_EXPR
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _image_url(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _images(value: Any) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for image in _as_list(value):
        if not isinstance(image, dict):
            continue
        normalized = {
            "small_url": _image_url(image.get("small_url") or image.get("small")),
            "medium_url": _image_url(image.get("medium_url") or image.get("medium")),
            "original_url": _image_url(
                image.get("original_url") or image.get("original") or image.get("large")
            ),
            "url": _image_url(image.get("url")),
            "label": image.get("classification_label") or image.get("label"),
        }
        if not any(
            normalized.get(key) for key in ("small_url", "medium_url", "original_url", "url")
        ):
            continue
        images.append(normalized)
    return images


def _primary_image(images: list[dict[str, Any]]) -> str | None:
    for image in images:
        for key in ("small_url", "medium_url", "original_url", "url"):
            if image.get(key):
                return str(image[key])
    return None


def _party(value: Any) -> ListingPartyResponse | None:
    data = _as_dict(value)
    if not data:
        return None
    normalized = {
        "id": None if data.get("id") is None else str(data.get("id")),
        "name": data.get("name"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "whatsapp": data.get("whatsapp"),
        "image_url": data.get("image_url") or data.get("image"),
        "logo_url": data.get("logo_url") or data.get("logo"),
        "address": data.get("address"),
        "slug": data.get("slug"),
        "is_super_agent": data.get("is_super_agent"),
        "languages": _as_list(data.get("languages")),
    }
    return ListingPartyResponse.model_validate(normalized)


def _floorplans(raw_property: dict[str, Any]) -> list[dict[str, Any]]:
    floorplans: list[dict[str, Any]] = []
    for item in _as_list(raw_property.get("floor_plans")):
        if not isinstance(item, dict):
            continue
        floorplans.append(
            {
                "title": item.get("title") or item.get("name"),
                "image_url": item.get("image_url") or item.get("url"),
                "area_sqft": _float_or_none(item.get("area")),
                "floor_number": _int_or_none(item.get("floor_number")),
                "unit_number": item.get("unit_number"),
                "dimension": item.get("dimension"),
            }
        )
    return floorplans


def _location_names(row: dict[str, Any]) -> list[str]:
    return [str(item) for item in _as_list(row.get("listing_location_names_json")) if item]


def _card_from_row(row: Any) -> ListingCardResponse:
    row = _row_to_dict(row)
    category_id = _int_or_none(row.get("category_id"))
    raw_property = _as_dict(row.get("raw_property_json"))
    price = _as_dict(row.get("price_json"))
    size = _as_dict(row.get("size_json"))
    names = _location_names(row)
    images = _images(row.get("images_json", row.get("images")))
    agent = _party(row.get("agent_json", row.get("agent")))
    broker = _party(row.get("broker_json", row.get("broker")))
    property_type = (
        raw_property.get("property_type")
        or row.get("property_type_name")
        or (str(row.get("property_type_id")) if row.get("property_type_id") is not None else None)
    )
    area_name, project_name, building_name = _location_hierarchy(names, property_type)
    listed_date = _parse_datetime(row.get("listed_at")) or _parse_datetime(
        raw_property.get("listed_date")
    )
    price_per_sqft = _float_or_none(row.get("price_per_sqft_aed"))
    market_psf = _float_or_none(row.get("market_median_price_per_sqft_aed"))
    market_estimate = _float_or_none(row.get("market_estimate_aed"))
    market_delta = _float_or_none(row.get("market_delta_pct"))
    comparable_count = _int_or_none(row.get("comparable_count")) or 0
    title = str(row.get("title") or raw_property.get("title") or "Untitled listing")
    listing_mode = _listing_mode(category_id)
    urgency_signal, urgency_terms = _urgency_terms(
        listing_mode,
        title,
        str(raw_property.get("description") or ""),
    )

    return ListingCardResponse(
        listing_id=str(row["listing_id"]),
        listing_mode=listing_mode,
        asset_class=_asset_class(category_id),
        title=title,
        reference=row.get("reference") or raw_property.get("reference"),
        property_type=property_type,
        price_value=_int_or_none(price.get("value")),
        price_currency=price.get("currency"),
        price_period=price.get("period"),
        size_value=_float_or_none(size.get("value")),
        size_unit=size.get("unit"),
        bedrooms=str(row.get("bedrooms")) if row.get("bedrooms") not in (None, "") else None,
        bathrooms=str(row.get("bathrooms")) if row.get("bathrooms") not in (None, "") else None,
        city_name=names[0] if len(names) > 0 else None,
        area_name=area_name,
        subcommunity_name=project_name,
        tower_name=building_name,
        location_name=", ".join(names) if names else None,
        latitude=_float_or_none(row.get("lat")),
        longitude=_float_or_none(row.get("lng")),
        primary_image_url=_primary_image(images),
        image_count=len(images),
        floorplan_count=len(_floorplans(raw_property)),
        agent_name=agent.name if agent else None,
        agent_image_url=agent.image_url if agent else None,
        broker_name=broker.name if broker else None,
        broker_logo_url=broker.logo_url if broker else None,
        listed_date=listed_date,
        listing_age_days=_int_or_none(row.get("listing_age_days")),
        price_per_sqft_aed=price_per_sqft,
        market_median_price_per_sqft_aed=market_psf,
        market_estimate_aed=market_estimate,
        market_delta_pct=market_delta,
        market_position=_market_position(market_delta, comparable_count),
        comparable_count=comparable_count,
        benchmark_level=_benchmark_level(property_type, comparable_count),
        urgency_signal=urgency_signal,
        urgency_terms=urgency_terms,
        is_available=_bool_or_none(row.get("is_available")),
        is_verified=_bool_or_none(row.get("is_verified")),
        is_featured=_bool_or_none(row.get("is_featured")),
        is_premium=_bool_or_none(row.get("is_premium")),
        share_url=row.get("share_url"),
    )


def _where_sql(
    mode: ListingMode,
    search: str | None,
    area: str | None,
    property_type: str | None,
    bedrooms: str | None,
    bedrooms_in: list[str] | None,
    price_min: int | None,
    price_max: int | None,
    asset_class: ListingAssetClass | None = None,
    price_period: str | None = None,
    price_basis: str = "raw",
) -> tuple[str, dict[str, Any]]:
    clauses = ["category_id IN {category_ids:Array(UInt16)}", "is_available = 1"]
    params: dict[str, Any] = {"category_ids": list(_category_ids(mode, asset_class))}
    price_filter_expr = _price_expr(_price_basis(price_basis))
    if search:
        clauses.append(
            """
            (
                positionCaseInsensitive(title, {search:String}) > 0
                OR positionCaseInsensitive(reference, {search:String}) > 0
                OR positionCaseInsensitive(listing_location_names_json, {search:String}) > 0
                OR positionCaseInsensitive(agent_json, {search:String}) > 0
                OR positionCaseInsensitive(broker_json, {search:String}) > 0
            )
            """
        )
        params["search"] = search.strip()
    if area:
        clauses.append(
            "JSONExtract(listing_location_names_json, 'Array(String)')[2] = {area:String}"
        )
        params["area"] = area
    if property_type:
        clauses.append("JSON_VALUE(raw_property_json, '$.property_type') = {property_type:String}")
        params["property_type"] = property_type
    if bedrooms_in:
        clauses.append("bedrooms IN {bedrooms:Array(String)}")
        params["bedrooms"] = bedrooms_in
    elif bedrooms:
        clauses.append("bedrooms = {bedrooms:String}")
        params["bedrooms"] = bedrooms
    if normalized_period := _price_period(price_period):
        clauses.append(f"{PRICE_PERIOD_EXPR} = {{price_period:String}}")
        params["price_period"] = normalized_period
    if price_min is not None:
        clauses.append(f"{price_filter_expr} >= {{price_min:Int64}}")
        params["price_min"] = price_min
    if price_max is not None:
        clauses.append(f"{price_filter_expr} <= {{price_max:Int64}}")
        params["price_max"] = price_max
    return " AND ".join(clauses), params


async def _filters(
    mode: ListingMode, asset_class: ListingAssetClass | None = None
) -> ListingFiltersResponse:
    params = {"category_ids": list(_category_ids(mode, asset_class))}
    modes_future = query(
        _listing_sql(
            """
        SELECT DISTINCT if(category_id IN (2, 4), 'rent', 'sale') AS listing_mode
        FROM {LISTINGS_TABLE}
        WHERE is_available = 1
        ORDER BY listing_mode
        """
        ),
        {},
    )
    areas_future = query(
        _listing_sql(
            """
        SELECT JSONExtract(listing_location_names_json, 'Array(String)')[2] AS area_name, count() AS n
        FROM {LISTINGS_TABLE}
        WHERE category_id IN {category_ids:Array(UInt16)}
          AND is_available = 1
          AND area_name != ''
        GROUP BY area_name
        ORDER BY n DESC, area_name ASC
        LIMIT 60
        """
        ),
        params,
    )
    property_types_future = query(
        _listing_sql(
            """
        SELECT JSON_VALUE(raw_property_json, '$.property_type') AS property_type, count() AS n
        FROM {LISTINGS_TABLE}
        WHERE category_id IN {category_ids:Array(UInt16)}
          AND is_available = 1
          AND property_type != ''
        GROUP BY property_type
        ORDER BY n DESC, property_type ASC
        LIMIT 40
        """
        ),
        params,
    )
    bedrooms_future = query(
        _listing_sql(
            """
        SELECT bedrooms
        FROM {LISTINGS_TABLE}
        WHERE category_id IN {category_ids:Array(UInt16)}
          AND is_available = 1
          AND bedrooms != ''
        GROUP BY bedrooms
        ORDER BY toInt32OrNull(bedrooms) ASC NULLS FIRST, bedrooms ASC
        """
        ),
        params,
    )
    prices_future = query(
        _listing_sql(
            """
        SELECT
            minIf({PRICE_VALUE_EXPR}, {PRICE_VALUE_EXPR} > 0)
                AS price_min,
            max({PRICE_VALUE_EXPR}) AS price_max
        FROM {LISTINGS_TABLE}
        WHERE category_id IN {category_ids:Array(UInt16)}
          AND is_available = 1
        """
        ),
        params,
    )
    (
        modes_result,
        areas_result,
        property_types_result,
        bedrooms_result,
        prices_result,
    ) = await asyncio.gather(
        modes_future,
        areas_future,
        property_types_future,
        bedrooms_future,
        prices_future,
    )
    prices = prices_result[0] if prices_result else {}
    return ListingFiltersResponse(
        modes=[row["listing_mode"] for row in modes_result],
        asset_classes=["residential", "commercial"],
        areas=[row["area_name"] for row in areas_result],
        property_types=[row["property_type"] for row in property_types_result],
        bedrooms=[row["bedrooms"] for row in bedrooms_result],
        price_min=_int_or_none(prices.get("price_min")),
        price_max=_int_or_none(prices.get("price_max")),
    )


async def listing_filters_from_clickhouse(
    mode: ListingMode, asset_class: ListingAssetClass | None = None
) -> ListingFiltersResponse:
    return await _filters(mode, asset_class)


def _next_month(period: str) -> str:
    parsed = datetime.strptime(f"{period}-01", "%Y-%m-%d")
    if parsed.month == 12:
        return f"{parsed.year + 1}-01-01"
    return f"{parsed.year}-{parsed.month + 1:02d}-01"


def _location_match_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _achieved_property_types(
    mode: ListingMode,
    asset_class: ListingAssetClass,
    property_type: str | None,
) -> list[str]:
    normalized = str(property_type or "").strip().lower()
    if mode == "rent":
        if asset_class == "commercial":
            return ["Commercial"]
        if normalized == "apartment":
            return ["Apartment"]
        if normalized in {"villa", "townhouse"}:
            return ["Villa"]
        return ["Apartment", "Villa"]

    if normalized == "apartment":
        return ["Apartment"]
    if normalized in {"villa", "townhouse"}:
        return ["Villa"]
    if normalized:
        title_type = normalized.title()
        if title_type in ACHIEVED_SALE_TYPES[asset_class]:
            return [title_type]
    return ACHIEVED_SALE_TYPES[asset_class]


async def _achieved_trend(
    *,
    mode: ListingMode,
    asset_class: ListingAssetClass,
    periods: list[str],
    area: str | None,
    property_type: str | None,
    bedrooms: str | None,
) -> list[dict[str, Any]]:
    if not periods:
        return []
    date_column = "lease_start" if mode == "rent" else "transaction_date"
    table = "dxbi_rental_events" if mode == "rent" else "dxbi_sales_unit_events"
    psf_expr = (
        "annual_rent_aed / size_sqft" if mode == "rent" else "price_per_sqft_aed"
    )
    psf_bounds = "BETWEEN 5 AND 2000" if mode == "rent" else "BETWEEN 200 AND 12000"
    clauses = [
        f"{date_column} >= {{achieved_start:Date}}",
        f"{date_column} < {{achieved_end:Date}}",
        "property_type IN {achieved_property_types:Array(String)}",
        "size_sqft > 0",
        f"{psf_expr} {psf_bounds}",
    ]
    params: dict[str, Any] = {
        "achieved_start": f"{periods[0]}-01",
        "achieved_end": _next_month(periods[-1]),
        "achieved_property_types": _achieved_property_types(
            mode, asset_class, property_type
        ),
    }
    if area_key := _location_match_key(area):
        clauses.append(
            "startsWith(lowerUTF8(replaceRegexpAll(area_name, '[^a-zA-Z0-9]', '')), "
            "{achieved_area_key:String})"
        )
        params["achieved_area_key"] = area_key
    if bedrooms:
        clauses.append("startsWith(lowerUTF8(bedrooms), {achieved_bedrooms:String})")
        params["achieved_bedrooms"] = bedrooms.strip().lower()

    return await query(
        f"""
        SELECT
            formatDateTime(toStartOfMonth({date_column}), '%Y-%m') AS period,
            quantileTDigest(0.5)({psf_expr}) AS median_achieved_price_per_sqft_aed,
            uniqExact({"event_key" if mode == "rent" else "sale_key"})
                AS achieved_transaction_count
        FROM {table} FINAL
        WHERE {" AND ".join(clauses)}
        GROUP BY period
        ORDER BY period ASC
        """,
        params,
    )


async def list_listings_from_clickhouse(
    mode: ListingMode,
    asset_class: ListingAssetClass | None = None,
    limit: int = 48,
    offset: int = 0,
    search: str | None = None,
    area: str | None = None,
    property_type: str | None = None,
    bedrooms: str | None = None,
    bedrooms_in: list[str] | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    price_period: str | None = None,
    price_basis: str = "raw",
    include_filters: bool = True,
) -> ListingListResponse:
    price_sort_expr = _price_expr(_price_basis(price_basis))
    market_price_expr = _market_price_expr(mode)
    where, params = _where_sql(
        mode=mode,
        asset_class=asset_class,
        search=search,
        area=area,
        property_type=property_type,
        bedrooms=bedrooms,
        bedrooms_in=bedrooms_in,
        price_min=price_min,
        price_max=price_max,
        price_period=price_period,
        price_basis=price_basis,
    )
    count_task = asyncio.create_task(
        query(
            f"""
            SELECT count() AS total
            FROM {LISTINGS_TABLE}
            WHERE {where}
            """,
            params,
        )
    )
    filters_task = asyncio.create_task(_filters(mode, asset_class)) if include_filters else None
    rows = await query(
        f"""
        SELECT
            listing_id,
            category_id,
            title,
            reference,
            property_type_id,
            price_json,
            size_json,
            bedrooms,
            bathrooms,
            listing_location_names_json,
            lat,
            lng,
            is_available,
            is_verified,
            is_featured,
            is_premium,
            share_url,
            agent_json,
            broker_json,
            client_json,
            images_json,
            raw_property_json,
            run_id,
            scraped_at,
            {AREA_NAME_EXPR} AS benchmark_area,
            {PROPERTY_TYPE_EXPR} AS benchmark_property_type,
            {PEER_LOCATION_EXPR} AS benchmark_peer_location,
            {SIZE_BUCKET_EXPR} AS benchmark_size_bucket,
            {VALID_BENCHMARK_SIZE_EXPR} AS has_valid_benchmark_size,
            {LISTED_AT_EXPR} AS listed_at,
            coalesce({SCRAPED_AT_EXPR}, now()) AS snapshot_at,
            {market_price_expr} AS market_price_aed,
            {SIZE_VALUE_EXPR} AS size_sqft,
            if(
                listed_at >= toDateTime('2010-01-01') AND listed_at <= snapshot_at,
                dateDiff('day', listed_at, snapshot_at),
                NULL
            ) AS listing_age_days,
            if(market_price_aed > 0 AND size_sqft > 0, market_price_aed / size_sqft, NULL)
                AS price_per_sqft_aed
        FROM {LISTINGS_TABLE}
        WHERE {where}
        ORDER BY
            is_featured DESC,
            is_premium DESC,
            snapshot_at DESC NULLS LAST,
            {price_sort_expr} ASC NULLS LAST
        LIMIT {{limit:Int32}} OFFSET {{offset:Int32}}
        """,
        {**params, "limit": limit, "offset": offset},
    )
    normalized_rows = [_row_to_dict(row) for row in rows]
    benchmark_property_types = sorted(
        {str(row.get("benchmark_property_type") or "") for row in normalized_rows}
    )
    benchmark_bedrooms = sorted({str(row.get("bedrooms") or "") for row in normalized_rows})
    benchmark_peer_locations = sorted(
        {str(row.get("benchmark_peer_location") or "") for row in normalized_rows}
    )
    benchmark_size_buckets = sorted(
        {_int_or_none(row.get("benchmark_size_bucket")) or 0 for row in normalized_rows}
    )
    benchmark_rows = []
    if normalized_rows:
        benchmark_rows = await query(
            f"""
            SELECT
                category_id,
                {PEER_LOCATION_EXPR} AS benchmark_peer_location,
                {PROPERTY_TYPE_EXPR} AS benchmark_property_type,
                bedrooms,
                {SIZE_BUCKET_EXPR} AS benchmark_size_bucket,
                quantileTDigest(0.5)({market_price_expr} / {SIZE_VALUE_EXPR})
                    AS market_median_price_per_sqft_aed,
                count() AS comparable_count
            FROM {LISTINGS_TABLE}
            WHERE category_id IN {{category_ids:Array(UInt16)}}
              AND is_available = 1
              AND {PEER_LOCATION_EXPR} IN {{benchmark_peer_locations:Array(String)}}
              AND {PROPERTY_TYPE_EXPR} IN {{benchmark_property_types:Array(String)}}
              AND bedrooms IN {{benchmark_bedrooms:Array(String)}}
              AND {SIZE_BUCKET_EXPR} IN {{benchmark_size_buckets:Array(UInt32)}}
              AND {VALID_BENCHMARK_SIZE_EXPR}
              AND {market_price_expr} > 0
              AND {SIZE_VALUE_EXPR} > 0
            GROUP BY
                category_id,
                benchmark_peer_location,
                benchmark_property_type,
                bedrooms,
                benchmark_size_bucket
            """,
            {
                "category_ids": params["category_ids"],
                "benchmark_peer_locations": benchmark_peer_locations,
                "benchmark_property_types": benchmark_property_types,
                "benchmark_bedrooms": benchmark_bedrooms,
                "benchmark_size_buckets": benchmark_size_buckets,
            },
        )
    benchmarks = {
        (
            _int_or_none(row.get("category_id")),
            str(row.get("benchmark_peer_location") or ""),
            str(row.get("benchmark_property_type") or ""),
            str(row.get("bedrooms") or ""),
            _int_or_none(row.get("benchmark_size_bucket")) or 0,
        ): row
        for row in benchmark_rows
    }
    for row in normalized_rows:
        key = (
            _int_or_none(row.get("category_id")),
            str(row.get("benchmark_peer_location") or ""),
            str(row.get("benchmark_property_type") or ""),
            str(row.get("bedrooms") or ""),
            _int_or_none(row.get("benchmark_size_bucket")) or 0,
        )
        benchmark = benchmarks.get(key, {}) if row.get("has_valid_benchmark_size") else {}
        market_psf = _float_or_none(benchmark.get("market_median_price_per_sqft_aed"))
        comparable_count = _int_or_none(benchmark.get("comparable_count")) or 0
        market_price = _float_or_none(row.get("market_price_aed"))
        size_sqft = _float_or_none(row.get("size_sqft"))
        row["market_median_price_per_sqft_aed"] = market_psf
        row["comparable_count"] = comparable_count
        if (
            comparable_count >= MIN_BENCHMARK_COMPARABLES
            and market_psf
            and market_price
            and size_sqft
        ):
            row["market_estimate_aed"] = market_psf * size_sqft
            row["market_delta_pct"] = market_price / size_sqft / market_psf - 1
    count_result = await count_task
    listing_filters = await filters_task if filters_task else ListingFiltersResponse()
    return ListingListResponse(
        listings=[_card_from_row(row) for row in normalized_rows],
        total=count_result[0]["total"] if count_result else 0,
        limit=limit,
        offset=offset,
        filters=listing_filters,
    )


async def listing_analytics_from_clickhouse(
    mode: ListingMode,
    asset_class: ListingAssetClass | None = None,
    search: str | None = None,
    area: str | None = None,
    property_type: str | None = None,
    bedrooms: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
) -> ListingAnalyticsResponse:
    """Return aggregate metrics for the same available-listing filter set as the grid."""
    market_price_expr = _market_price_expr(mode)
    where, params = _where_sql(
        mode=mode,
        asset_class=asset_class,
        search=search,
        area=area,
        property_type=property_type,
        bedrooms=bedrooms,
        bedrooms_in=None,
        price_min=price_min,
        price_max=price_max,
        price_basis="annual" if mode == "rent" else "raw",
    )
    result_future = query(
        f"""
        SELECT
            count() AS total,
            avgIf(market_price_aed, market_price_aed > 0) AS average_price_aed,
            quantileTDigestIf(0.5)(market_price_aed, market_price_aed > 0)
                AS median_price_aed,
            quantileTDigestIf(0.5)(price_per_sqft_aed, price_per_sqft_aed > 0)
                AS median_price_per_sqft_aed,
            avgIf(listing_age_days, listing_age_days IS NOT NULL) AS average_listing_age_days,
            quantileTDigestIf(0.5)(listing_age_days, listing_age_days IS NOT NULL)
                AS median_listing_age_days,
            countIf(listing_age_days BETWEEN 0 AND 30) AS newly_listed_30d,
            countIf(
                comparable_count >= {MIN_BENCHMARK_COMPARABLES}
                AND market_delta_pct < {-MARKET_POSITION_THRESHOLD}
            ) AS below_market_count,
            countIf(
                comparable_count >= {MIN_BENCHMARK_COMPARABLES}
                AND market_delta_pct BETWEEN {-MARKET_POSITION_THRESHOLD}
                    AND {MARKET_POSITION_THRESHOLD}
            ) AS near_market_count,
            countIf(
                comparable_count >= {MIN_BENCHMARK_COMPARABLES}
                AND market_delta_pct > {MARKET_POSITION_THRESHOLD}
            ) AS above_market_count,
            countIf(comparable_count >= {MIN_BENCHMARK_COMPARABLES}) AS benchmarked_count,
            countIf(is_verified = 1) AS verified_count,
            uniqExact(benchmark_area) AS area_count,
            max(snapshot_at) AS snapshot_at
        FROM (
            SELECT
                inventory.*,
                if(
                    inventory.listed_at >= toDateTime('2010-01-01')
                    AND inventory.listed_at <= inventory.snapshot_at,
                    dateDiff('day', inventory.listed_at, inventory.snapshot_at),
                    NULL
                ) AS listing_age_days,
                if(
                    inventory.market_price_aed > 0 AND inventory.size_sqft > 0,
                    inventory.market_price_aed / inventory.size_sqft,
                    NULL
                ) AS price_per_sqft_aed,
                benchmarks.comparable_count,
                if(
                    inventory.has_valid_benchmark_size
                    AND inventory.benchmark_peer_location != ''
                    AND
                    benchmarks.comparable_count >= {MIN_BENCHMARK_COMPARABLES}
                    AND benchmarks.market_median_price_per_sqft_aed > 0
                    AND inventory.market_price_aed > 0
                    AND inventory.size_sqft > 0,
                    (inventory.market_price_aed / inventory.size_sqft)
                        / benchmarks.market_median_price_per_sqft_aed - 1,
                    NULL
                ) AS market_delta_pct
            FROM (
                SELECT
                    category_id,
                    is_verified,
                    {AREA_NAME_EXPR} AS benchmark_area,
                    {PEER_LOCATION_EXPR} AS benchmark_peer_location,
                    {PROPERTY_TYPE_EXPR} AS benchmark_property_type,
                    bedrooms,
                    {SIZE_BUCKET_EXPR} AS benchmark_size_bucket,
                    {VALID_BENCHMARK_SIZE_EXPR} AS has_valid_benchmark_size,
                    {LISTED_AT_EXPR} AS listed_at,
                    coalesce({SCRAPED_AT_EXPR}, now()) AS snapshot_at,
                    {market_price_expr} AS market_price_aed,
                    {SIZE_VALUE_EXPR} AS size_sqft
                FROM {LISTINGS_TABLE}
                WHERE {where}
            ) AS inventory
            LEFT JOIN (
                SELECT
                    category_id,
                    {PEER_LOCATION_EXPR} AS benchmark_peer_location,
                    {PROPERTY_TYPE_EXPR} AS benchmark_property_type,
                    bedrooms,
                    {SIZE_BUCKET_EXPR} AS benchmark_size_bucket,
                    quantileTDigest(0.5)({market_price_expr} / {SIZE_VALUE_EXPR})
                        AS market_median_price_per_sqft_aed,
                    count() AS comparable_count
                FROM {LISTINGS_TABLE}
                WHERE category_id IN {{category_ids:Array(UInt16)}}
                  AND is_available = 1
                  AND {PEER_LOCATION_EXPR} != ''
                  AND {VALID_BENCHMARK_SIZE_EXPR}
                  AND {market_price_expr} > 0
                  AND {SIZE_VALUE_EXPR} > 0
                GROUP BY
                    category_id,
                    benchmark_peer_location,
                    benchmark_property_type,
                    bedrooms,
                    benchmark_size_bucket
            ) AS benchmarks
              ON inventory.category_id = benchmarks.category_id
             AND inventory.benchmark_peer_location = benchmarks.benchmark_peer_location
             AND inventory.benchmark_property_type = benchmarks.benchmark_property_type
             AND inventory.bedrooms = benchmarks.bedrooms
             AND inventory.benchmark_size_bucket = benchmarks.benchmark_size_bucket
        )
        """,
        params,
    )
    trend_future = query(
        f"""
        SELECT
            formatDateTime(toStartOfMonth(listed_at), '%Y-%m') AS period,
            avg(market_price_aed) AS average_asking_price_aed,
            quantileTDigest(0.5)(market_price_aed) AS median_asking_price_aed,
            quantileTDigestIf(0.5)(
                market_price_aed / size_sqft,
                size_sqft > 0
            ) AS median_price_per_sqft_aed,
            count() AS listing_count
        FROM (
            SELECT
                {LISTED_AT_EXPR} AS listed_at,
                coalesce({SCRAPED_AT_EXPR}, now()) AS snapshot_at,
                {market_price_expr} AS market_price_aed,
                {SIZE_VALUE_EXPR} AS size_sqft
            FROM {LISTINGS_TABLE}
            WHERE {where}
        )
        WHERE listed_at >= toDateTime('2010-01-01')
          AND listed_at <= snapshot_at
          AND listed_at >= addMonths(toStartOfMonth(snapshot_at), -11)
          AND market_price_aed > 0
        GROUP BY period
        ORDER BY period ASC
        """,
        params,
    )
    result, trend_result = await asyncio.gather(result_future, trend_future)
    trend_periods = [str(point.get("period") or "") for point in trend_result if point.get("period")]
    achieved_rows = await _achieved_trend(
        mode=mode,
        asset_class=asset_class or "residential",
        periods=trend_periods,
        area=area,
        property_type=property_type,
        bedrooms=bedrooms,
    )
    achieved_by_period = {
        str(point.get("period") or ""): point for point in achieved_rows if point.get("period")
    }
    row = result[0] if result else {}
    return ListingAnalyticsResponse(
        total=_int_or_none(row.get("total")) or 0,
        average_price_aed=_float_or_none(row.get("average_price_aed")),
        median_price_aed=_float_or_none(row.get("median_price_aed")),
        median_price_per_sqft_aed=_float_or_none(row.get("median_price_per_sqft_aed")),
        average_listing_age_days=_float_or_none(row.get("average_listing_age_days")),
        median_listing_age_days=_float_or_none(row.get("median_listing_age_days")),
        newly_listed_30d=_int_or_none(row.get("newly_listed_30d")) or 0,
        below_market_count=_int_or_none(row.get("below_market_count")) or 0,
        near_market_count=_int_or_none(row.get("near_market_count")) or 0,
        above_market_count=_int_or_none(row.get("above_market_count")) or 0,
        benchmarked_count=_int_or_none(row.get("benchmarked_count")) or 0,
        verified_count=_int_or_none(row.get("verified_count")) or 0,
        area_count=_int_or_none(row.get("area_count")) or 0,
        snapshot_at=_parse_datetime(row.get("snapshot_at")),
        trend=[
            ListingTrendPoint(
                period=str(point.get("period") or ""),
                average_asking_price_aed=_float_or_none(point.get("average_asking_price_aed")),
                median_asking_price_aed=_float_or_none(point.get("median_asking_price_aed")),
                median_price_per_sqft_aed=_float_or_none(point.get("median_price_per_sqft_aed")),
                listing_count=_int_or_none(point.get("listing_count")) or 0,
                median_achieved_price_per_sqft_aed=_float_or_none(
                    achieved_by_period.get(str(point.get("period") or ""), {}).get(
                        "median_achieved_price_per_sqft_aed"
                    )
                ),
                achieved_transaction_count=_int_or_none(
                    achieved_by_period.get(str(point.get("period") or ""), {}).get(
                        "achieved_transaction_count"
                    )
                )
                or 0,
            )
            for point in trend_result
            if point.get("period")
        ],
    )


async def get_listing_from_clickhouse(listing_id: str) -> ListingDetailResponse:
    rows = await query(
        _listing_sql(
            """
        SELECT
            listing_id,
            category_id,
            title,
            reference,
            property_type_id,
            price_json,
            size_json,
            bedrooms,
            bathrooms,
            listing_location_names_json,
            lat,
            lng,
            is_available,
            is_verified,
            is_featured,
            is_premium,
            share_url,
            agent_json,
            broker_json,
            client_json,
            images_json,
            raw_property_json,
            raw_wrapper_json,
            run_id,
            scraped_at
        FROM {LISTINGS_TABLE}
        WHERE listing_id = {listing_id:String}
        LIMIT 1
        """
        ),
        {"listing_id": listing_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Listing not found")

    data = rows[0]
    raw_property = _as_dict(data.get("raw_property_json"))
    card = _card_from_row(data)
    amenities = raw_property.get("amenity_names") or raw_property.get("amenities")
    return ListingDetailResponse(
        **card.model_dump(),
        description=raw_property.get("description"),
        amenities=[str(item) for item in _as_list(amenities) if item],
        images=[
            ListingImageResponse.model_validate(item) for item in _images(data.get("images_json"))
        ],
        floorplans=[
            ListingFloorPlanResponse.model_validate(item) for item in _floorplans(raw_property)
        ],
        agent=_party(data.get("agent_json")),
        broker=_party(data.get("broker_json")),
        client=_party(data.get("client_json")),
        furnished=raw_property.get("furnished"),
        completion_status=raw_property.get("completion_status"),
        rera=raw_property.get("rera"),
        number_of_cheques=_int_or_none(raw_property.get("number_of_cheques")),
        payment_method=[str(item) for item in _as_list(raw_property.get("payment_method"))],
        video_url=raw_property.get("video_url"),
        view_360_url=raw_property.get("view_360"),
        source_run_id=data.get("run_id"),
        source_manifest_key=None,
        scraped_at=_parse_datetime(data.get("scraped_at")),
        source_metadata={
            "source": LISTINGS_SOURCE_LABEL,
            "run_id": data.get("run_id"),
        },
    )
