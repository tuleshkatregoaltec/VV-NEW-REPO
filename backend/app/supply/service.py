"""Supply service for upcoming projects and ph_box-backed supply catalogue."""

import json
import logging
import re
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.clickhouse.client import query
from app.core.market_constants import SQM_TO_SQFT
from app.core.normalization import (
    developer_brand_name,
    developer_match_key,
    is_rankable_developer_brand,
)
from app.core.reelly_scope import reelly_dubai_project_scope
from app.supply.models import (
    DeveloperRankingCriterionResponse,
    DeveloperRankingResponse,
    DeveloperRankingsResponse,
    DeveloperRankingSummaryResponse,
    SupplyCatalogueAssetResponse,
    SupplyCatalogueBuildingResponse,
    SupplyCatalogueFinancialMetricResponse,
    SupplyCatalogueNearbyPointResponse,
    SupplyCataloguePaymentStepResponse,
    SupplyCatalogueProjectCardResponse,
    SupplyCatalogueProjectDetailResponse,
    SupplyCatalogueProjectsResponse,
    SupplyCatalogueRiskIndicatorResponse,
    SupplyCatalogueUnitResponse,
)

logger = logging.getLogger(__name__)

SUPPLY_CATALOGUE_GALLERY_ASSET_TYPES = (
    "building_image",
    "interior_image",
    "facility_image",
    "unit_image",
)
DEVELOPER_RANKING_PERIODS: dict[str, tuple[str, int | None]] = {
    "ytd": ("Year to date", None),
    "1y": ("Last 12 months", 365),
    "3y": ("Last 3 years", 365 * 3),
    "5y": ("Last 5 years", 365 * 5),
}
DEVELOPER_RANKING_METRICS = {
    "proprietary_score",
    "units_sold",
    "sales_volume",
    "avg_price_sqft",
    "pipeline_units",
    "active_projects",
    "completed_projects",
    "avg_completion_pct",
}
DEVELOPER_SCORE_WEIGHTS = {
    "delivered_unit_scale": 20.0,
    "pipeline_unit_scale": 15.0,
    "on_time_delivery": 65.0,
}
DEVELOPER_SCORE_MIN_WEIGHT = 40.0
DEVELOPER_DELIVERED_UNIT_FULL_SCORE = 10_000
DEVELOPER_PIPELINE_UNIT_FULL_SCORE = 15_000
# Note for follow-up: Q Properties is hidden from developer rankings pending
# validation of its developer grouping and source-data quality.
DEVELOPER_RANKING_HIDDEN_DEVELOPER_KEYS = {"properties"}
PROJECT_SCORE_MIN_COVERAGE = 35.0
PROJECT_RISK_WEIGHTS = {
    "developer": 35.0,
    "delivery": 25.0,
    "progress": 20.0,
    "sales": 20.0,
}
SUPPLY_CATALOGUE_SORTS = {
    "recommended",
    "newest",
    "price_low",
    "price_high",
    "delivery_soon",
    "delivery_latest",
}


async def get_upcoming_projects_ch(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Get all active/upcoming projects from ClickHouse.
    Active = delivery date after the latest loaded DLD sales date and no cancellation.
    """
    try:
        anchor_date = await _latest_sales_date() or date.today()
        sql = """
            SELECT
                p.project_id,
                p.project_name_en,
                p.developer_id,
                d.developer_name_en as developer_name,
                p.area_name_en,
                p.project_start_date,
                p.project_end_date,
                p.percent_completed,
                p.no_of_buildings,
                p.no_of_units
            FROM ch_projects p
            LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
            WHERE
                coalesce(p.no_of_units, 0) > 0
                AND coalesce(p.completion_date, p.project_end_date) > {anchor_date:Date}
                AND p.cancellation_date IS NULL
            ORDER BY
                coalesce(p.completion_date, p.project_end_date) ASC NULLS LAST,
                p.project_name_en ASC
            LIMIT {limit:Int32}
            OFFSET {offset:Int32}
        """
        params = {"anchor_date": anchor_date.isoformat(), "limit": limit, "offset": offset}

        result = await query(sql, params)
        return result

    except Exception as e:
        logger.error(f"Error fetching upcoming projects from ClickHouse: {str(e)}")
        return []


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _row_data(row: Any) -> dict[str, Any]:
    return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _flatten_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        values: list[Any] = []
        for item in value:
            values.extend(_flatten_values(item))
        return values
    return [value]


def _text_or_none(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def _stable_asset_id(project_id: int, asset_type: str, index: int) -> int:
    namespace = {
        "cover_image": 1,
        "building_image": 2,
        "interior_image": 3,
        "facility_image": 4,
        "unit_image": 5,
        "floorplan": 6,
        "brochure": 7,
        "master_plan": 8,
    }.get(asset_type, 9)
    return project_id * 1000 + namespace * 100 + index


def _asset_from_url(
    project_id: int,
    asset_type: str,
    index: int,
    url: str,
    name: str | None = None,
    content_type: str | None = None,
    size_bytes: int | None = None,
) -> SupplyCatalogueAssetResponse:
    is_document = asset_type in {"brochure", "floorplan"}
    return SupplyCatalogueAssetResponse(
        id=_stable_asset_id(project_id, asset_type, index),
        asset_type=asset_type,
        name=name,
        url=url,
        download_url=url if is_document else None,
        content_type=content_type,
        size_bytes=size_bytes,
    )


def _assets_from_reelly_value(
    project_id: int, asset_type: str, value: Any
) -> list[SupplyCatalogueAssetResponse]:
    assets: list[SupplyCatalogueAssetResponse] = []
    seen_urls: set[str] = set()
    for item in _flatten_values(value):
        url: str | None = None
        name: str | None = None
        content_type: str | None = None
        size_bytes: int | None = None
        if isinstance(item, dict):
            url = _text_or_none(item.get("url"))
            name = _text_or_none(item.get("name"))
            content_type = _text_or_none(item.get("mime"))
            size_bytes = _int_or_none(item.get("size"))
        elif isinstance(item, str) and item.startswith(("http://", "https://")):
            url = item
            name = item.rsplit("/", 1)[-1] or None

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        assets.append(
            _asset_from_url(
                project_id=project_id,
                asset_type=asset_type,
                index=len(assets) + 1,
                url=url,
                name=name,
                content_type=content_type,
                size_bytes=size_bytes,
            )
        )
    return assets


def _facility_assets(
    project_id: int, facilities: Any
) -> tuple[list[str], list[SupplyCatalogueAssetResponse]]:
    names: list[str] = []
    assets: list[SupplyCatalogueAssetResponse] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for item in _flatten_values(facilities):
        if not isinstance(item, dict):
            continue
        name = _text_or_none(item.get("Name"))
        if name and name.lower() not in seen_names:
            seen_names.add(name.lower())
            names.append(name)
        for image_asset in _assets_from_reelly_value(
            project_id, "facility_image", item.get("Image")
        ):
            if image_asset.url in seen_urls:
                continue
            seen_urls.add(image_asset.url)
            assets.append(
                image_asset.model_copy(
                    update={"id": _stable_asset_id(project_id, "facility_image", len(assets) + 1)}
                )
            )
    return names, assets


def _unit_type_names(value: Any) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in _flatten_values(value):
        name = _text_or_none(item)
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _unit_responses(raw: dict[str, Any], list_item: dict[str, Any]) -> list[dict[str, Any]]:
    unit_types = _unit_type_names(raw.get("Units_types") or list_item.get("Units_types"))
    prices = [
        item for item in _flatten_values(list_item.get("Starting_price")) if isinstance(item, dict)
    ]
    units: list[dict[str, Any]] = []
    for index, price in enumerate(prices):
        label = unit_types[index] if index < len(unit_types) else f"Unit type {index + 1}"
        units.append(
            {
                "label": label,
                "unit_type": label,
                "price_from_aed": _int_or_none(price.get("Price_from_AED")),
                "price_to_aed": _int_or_none(price.get("Price_to_AED")),
            }
        )
    if not units:
        units = [{"label": item, "unit_type": item} for item in unit_types]
    return units


def _payment_plan(raw: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for item in _flatten_values(raw.get("Payment_plans")):
        if not isinstance(item, dict):
            continue
        label = _text_or_none(item.get("Payment_time") or item.get("Name") or item.get("The"))
        percent = _text_or_none(item.get("Percent_of_payment"))
        if not label and percent:
            label = f"{percent}% payment"
        if not label:
            continue
        steps.append(
            {
                "label": label,
                "percent": percent,
                "order": _int_or_none(item.get("Order")),
            }
        )
    return sorted(steps, key=lambda item: item.get("order") or 999)


def _coordinates(value: Any) -> dict[str, float] | None:
    text_value = _text_or_none(value)
    if not text_value or "," not in text_value:
        return None
    latitude, longitude = [part.strip() for part in text_value.split(",", 1)]
    lat = _float_or_none(latitude)
    lng = _float_or_none(longitude)
    if lat is None or lng is None:
        return None
    return {"latitude": lat, "longitude": lng}


def _catalogue_data_from_clickhouse_row(row: dict[str, Any]) -> dict[str, Any]:
    list_item = _json_dict(row.get("list_item_json"))
    raw = _json_dict(row.get("raw_json"))
    project_id = (
        _int_or_none(row.get("project_id"))
        or _int_or_none(list_item.get("id"))
        or _int_or_none(row.get("project_key"))
    )
    if project_id is None:
        raise ValueError("Reelly project row is missing a numeric project id")

    units = _unit_responses(raw, list_item)
    unit_types = _unit_type_names(raw.get("Units_types") or list_item.get("Units_types"))
    cover_image_url = _text_or_none(
        (list_item.get("cover") or {}).get("url")
        if isinstance(list_item.get("cover"), dict)
        else None
    )
    if not cover_image_url:
        cover_image_url = _text_or_none(raw.get("cover_url"))

    gallery = _assets_from_reelly_value(project_id, "building_image", raw.get("Architecture"))
    floorplans = _assets_from_reelly_value(
        project_id, "floorplan", raw.get("Layouts_preview_img") or raw.get("Units_layouts_PDF")
    )
    brochures = _assets_from_reelly_value(project_id, "brochure", raw.get("Brochure"))
    master_plans = _assets_from_reelly_value(project_id, "master_plan", raw.get("Master_plan"))
    facilities, facility_assets = _facility_assets(project_id, raw.get("Facilities"))
    gallery = (gallery + facility_assets)[:18]

    min_price = _int_or_none(list_item.get("min_price") or raw.get("min_price"))
    if min_price in (None, 0):
        price_candidates = [
            _int_or_none(item.get("Price_from_AED"))
            for item in _flatten_values(list_item.get("Starting_price"))
            if isinstance(item, dict)
        ]
        price_candidates = [item for item in price_candidates if item and item > 0]
        min_price = min(price_candidates) if price_candidates else None
    max_price = _int_or_none(list_item.get("max_price") or raw.get("max_price"))

    overview = _text_or_none(raw.get("Overview"))
    return {
        "project_id": project_id,
        "project_name": _text_or_none(list_item.get("Project_name") or raw.get("Project_name"))
        or f"Project {project_id}",
        "developer_name": _text_or_none(
            list_item.get("Developers_name") or raw.get("Developers_name")
        )
        or "Unknown developer",
        "developer_id": None,
        "area_name": _text_or_none(list_item.get("Area_name") or raw.get("Area_name")),
        "region": "Dubai",
        "status": _text_or_none(list_item.get("Status") or raw.get("Status")),
        "sale_status": _text_or_none(list_item.get("sale_status") or raw.get("sale_status")),
        "completion_date": _text_or_none(
            list_item.get("Completion_date") or raw.get("Completion_date")
        ),
        "completion_time_ms": _int_or_none(
            list_item.get("Completion_time") or raw.get("Completion_time")
        ),
        "min_price_aed": min_price,
        "max_price_aed": max_price,
        "units_in_sale": _int_or_none(list_item.get("units_in_sale") or raw.get("units_in_sale")),
        "unit_types": unit_types,
        "units": units,
        "payment_plan": _payment_plan(raw),
        "facilities": facilities,
        "buildings": [],
        "nearby_points": [],
        "overview": overview,
        "overview_excerpt": overview[:240] if overview else None,
        "coordinates": _coordinates(raw.get("Coordinates")),
        "cover_image_url": cover_image_url,
        "developer_logo_url": None,
        "image_count": len(gallery),
        "floorplan_count": len(floorplans),
        "brochure_count": len(brochures),
        "gallery": gallery,
        "floorplans": floorplans,
        "brochures": brochures,
        "master_plans": master_plans,
        "raw": raw,
        "source_run_id": row.get("run_id"),
        "scraped_at": row.get("scraped_at"),
    }


def _card_from_row(
    row: Any,
    developer_scores: dict[str, DeveloperRankingResponse] | None = None,
    dld_signals: dict[int, dict[str, Any]] | None = None,
) -> SupplyCatalogueProjectCardResponse:
    data = _row_data(row)
    developer_scores = developer_scores or {}
    dld_signal = (dld_signals or {}).get(int(data["project_id"]))
    launch_date = _reelly_launch_date(data)
    sales_inventory = _project_sales_inventory(data, dld_signal)
    risk_indicators = [
        _developer_indicator(data, developer_scores),
        _launch_indicator(data, dld_signal),
        _delivery_indicator(data, dld_signal),
        _progress_indicator(dld_signal),
        _sales_indicator(data, dld_signal),
    ]
    project_score, score_coverage = _score_weighted_indicators(risk_indicators)
    developer = developer_scores.get(_developer_logo_match_key(data.get("developer_name")))

    return SupplyCatalogueProjectCardResponse(
        project_id=data["project_id"],
        project_name=data["project_name"],
        developer_name=data.get("developer_name") or "Unknown developer",
        developer_id=data.get("developer_id"),
        area_name=data.get("area_name"),
        region=data.get("region"),
        status=data.get("status"),
        sale_status=data.get("sale_status"),
        completion_date=data.get("completion_date"),
        launch_date=launch_date.isoformat() if launch_date else None,
        min_price_aed=data.get("min_price_aed"),
        max_price_aed=data.get("max_price_aed"),
        units_in_sale=data.get("units_in_sale"),
        units_sold=sales_inventory.get("units_sold"),
        units_unsold=sales_inventory.get("units_unsold"),
        total_units=sales_inventory.get("total_units"),
        registered_units=sales_inventory.get("registered_units"),
        sales_absorption_pct=sales_inventory.get("sales_absorption_pct"),
        sales_inventory_source=sales_inventory.get("source"),
        unit_types=_as_list(data.get("unit_types")),
        overview_excerpt=data.get("overview_excerpt"),
        cover_image_url=data.get("cover_image_url"),
        developer_logo_url=data.get("developer_logo_url"),
        image_count=data.get("image_count") or 0,
        floorplan_count=data.get("floorplan_count") or 0,
        brochure_count=data.get("brochure_count") or 0,
        project_score=project_score,
        project_risk_badge=_project_risk_badge(project_score, score_coverage),
        score_coverage_pct=score_coverage,
        developer_score=developer.proprietary_score if developer else None,
        developer_risk_badge=developer.risk_badge if developer else None,
        risk_indicators=risk_indicators,
    )


def _developer_logo_match_key(value: str | None) -> str:
    return developer_match_key(value)


def _developer_ranking_hidden(developer_name: str | None) -> bool:
    return _developer_logo_match_key(developer_name) in DEVELOPER_RANKING_HIDDEN_DEVELOPER_KEYS


def _developer_brand_name(developer_name: str) -> str:
    return developer_brand_name(developer_name)


def _developer_rankable_brand(developer_name: str) -> bool:
    return is_rankable_developer_brand(developer_name)


def _text_tokens(value: str | None) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return {part for part in normalized.split() if len(part) > 2}


def _token_overlap(left: str | None, right: str | None) -> float:
    left_tokens = _text_tokens(left)
    right_tokens = _text_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _parse_catalogue_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text_value = str(value or "").strip()
    if not text_value:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(text_value, pattern)
            return parsed.date()
        except ValueError:
            pass
    match = re.search(r"\b(20\d{2})\b", text_value)
    if match:
        return date(int(match.group(1)), 12, 31)
    return None


def _parse_epoch_date(value: Any) -> date | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
    except (OSError, OverflowError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _raw_payload(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("raw")
    return raw if isinstance(raw, dict) else {}


def _reelly_launch_date(data: dict[str, Any]) -> date | None:
    raw = _raw_payload(data)
    return (
        _parse_epoch_date(raw.get("Launch_date"))
        or _parse_epoch_date(raw.get("launch_date"))
        or _parse_catalogue_date(raw.get("Launch_date"))
    )


def _reelly_unsold_units(data: dict[str, Any]) -> int | None:
    raw = _raw_payload(data)
    parsed = _int_or_none(data.get("units_in_sale"))
    if parsed is None:
        parsed = _int_or_none(raw.get("units_in_sale"))
    if parsed is None:
        return None
    sale_status = str(data.get("sale_status") or raw.get("sale_status") or "").lower()
    if parsed == 0 and "out of stock" not in sale_status:
        return None
    return max(parsed, 0)


def _reelly_unit_total(data: dict[str, Any]) -> int | None:
    total = 0
    for item in _as_list(data.get("units")):
        if not isinstance(item, dict):
            continue
        units_amount = _int_or_none(item.get("units_amount"))
        if units_amount is not None and units_amount > 0:
            total += units_amount
    return total if total > 0 else None


def _project_sales_inventory(
    data: dict[str, Any], dld_signal: dict[str, Any] | None
) -> dict[str, Any]:
    unsold_units = _reelly_unsold_units(data)
    registered_units = _int_or_none((dld_signal or {}).get("no_of_units"))
    reelly_total_units = _reelly_unit_total(data)
    total_units = (
        registered_units if registered_units and registered_units > 0 else reelly_total_units
    )
    sold_units = None
    absorption_pct = None

    if total_units is not None and unsold_units is not None:
        sold_units = max(total_units - unsold_units, 0)
        absorption_pct = round(min(sold_units / total_units * 100, 100.0), 1)

    if registered_units and unsold_units is not None:
        source = "Live inventory against DLD registered units."
    elif reelly_total_units and unsold_units is not None:
        source = "Live inventory against catalogue unit count."
    elif unsold_units is not None:
        source = "Live inventory count."
    elif registered_units:
        source = "DLD registered units; live inventory pending."
    else:
        source = None

    return {
        "units_sold": sold_units,
        "units_unsold": unsold_units,
        "total_units": total_units,
        "registered_units": registered_units,
        "sales_absorption_pct": absorption_pct,
        "source": source,
    }


def _format_indicator_pct(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{round(value):.0f}%"


def _indicator_status(score: float | None, available: bool = True) -> str:
    if not available or score is None:
        return "Pending"
    if score >= 75:
        return "Low"
    if score >= 55:
        return "Medium"
    return "High"


def _risk_indicator(
    *,
    key: str,
    label: str,
    value: str | None,
    score: float | None,
    note: str | None = None,
    available: bool = True,
) -> SupplyCatalogueRiskIndicatorResponse:
    return SupplyCatalogueRiskIndicatorResponse(
        key=key,
        label=label,
        value=value,
        score=score,
        status=_indicator_status(score, available),
        available=available,
        note=note,
    )


def _project_risk_badge(score: float | None, coverage: float) -> str:
    if score is None or coverage < PROJECT_SCORE_MIN_COVERAGE:
        return "Review"
    if score >= 78:
        return "Low"
    if score >= 58:
        return "Medium"
    return "High"


def _score_weighted_indicators(
    indicators: list[SupplyCatalogueRiskIndicatorResponse],
) -> tuple[float | None, float]:
    weighted_score = 0.0
    available_weight = 0.0
    for indicator in indicators:
        weight = PROJECT_RISK_WEIGHTS.get(indicator.key)
        if weight is None or indicator.score is None or not indicator.available:
            continue
        weighted_score += indicator.score * weight
        available_weight += weight
    if available_weight <= 0:
        return None, 0.0
    return round(weighted_score / available_weight, 1), round(available_weight, 1)


def _launch_indicator(
    data: dict[str, Any], dld_signal: dict[str, Any] | None
) -> SupplyCatalogueRiskIndicatorResponse:
    launch_date = _reelly_launch_date(data)
    if not launch_date:
        return _risk_indicator(
            key="launch",
            label="Launch date",
            value="~",
            score=None,
            available=False,
            note="Launch date pending.",
        )

    anchor = dld_signal.get("anchor_date") if dld_signal else None
    anchor_date = anchor if isinstance(anchor, date) else date.today()
    days_since_launch = (anchor_date - launch_date).days
    if days_since_launch < -30:
        score = 72.0
        note = "Forward launch date."
    elif days_since_launch <= 180:
        score = 84.0
        note = "Recent launch window."
    elif days_since_launch <= 730:
        score = 78.0
        note = "Launch date is within the current sales cycle."
    else:
        score = 66.0
        note = "Older launch; absorption should be reviewed against remaining inventory."

    return _risk_indicator(
        key="launch",
        label="Launch date",
        value=launch_date.isoformat(),
        score=score,
        note=note,
    )


def _delivery_indicator(
    data: dict[str, Any], dld_signal: dict[str, Any] | None
) -> SupplyCatalogueRiskIndicatorResponse:
    delivery_date = _parse_catalogue_date(data.get("completion_date")) or _parse_catalogue_date(
        dld_signal.get("project_end_date") if dld_signal else None
    )
    anchor = dld_signal.get("anchor_date") if dld_signal else None
    anchor_date = anchor if isinstance(anchor, date) else date.today()
    if not delivery_date:
        return _risk_indicator(
            key="delivery",
            label="Delivery timing",
            value="~",
            score=None,
            available=False,
            note="Delivery date feed pending.",
        )
    months_left = (
        (delivery_date.year - anchor_date.year) * 12 + delivery_date.month - anchor_date.month
    )
    if months_left < 0:
        score = 48.0
        note = "Stated delivery is behind the current data window."
    elif months_left <= 6:
        score = 68.0
        note = "Near-term delivery window."
    elif months_left <= 36:
        score = 84.0
        note = "Delivery window aligns with active pipeline monitoring."
    else:
        score = 72.0
        note = "Longer-dated pipeline exposure."
    return _risk_indicator(
        key="delivery",
        label="Delivery timing",
        value=delivery_date.isoformat(),
        score=score,
        note=note,
    )


def _progress_indicator(dld_signal: dict[str, Any] | None) -> SupplyCatalogueRiskIndicatorResponse:
    progress = _float_or_none(dld_signal.get("percent_completed") if dld_signal else None)
    if progress is None:
        return _risk_indicator(
            key="progress",
            label="Construction progress",
            value="~",
            score=None,
            available=False,
            note="DLD project progress match pending.",
        )
    score = _score_value(55 + min(progress, 100) * 0.45)
    return _risk_indicator(
        key="progress",
        label="Construction progress",
        value=_format_indicator_pct(progress),
        score=score,
        note="Matched to DLD project progress where available.",
    )


def _sales_indicator(
    data: dict[str, Any], dld_signal: dict[str, Any] | None
) -> SupplyCatalogueRiskIndicatorResponse:
    inventory = _project_sales_inventory(data, dld_signal)
    sold_units = inventory.get("units_sold")
    unsold_units = inventory.get("units_unsold")
    total_units = inventory.get("total_units")
    absorption_pct = inventory.get("sales_absorption_pct")
    source = inventory.get("source")
    sale_status = str(data.get("sale_status") or "").lower()
    launch_date = _reelly_launch_date(data)

    if sold_units is None and unsold_units is None and total_units is None:
        return _risk_indicator(
            key="sales",
            label="Sales absorption",
            value="~",
            score=None,
            available=False,
            note="Sold/unsold unit feed pending.",
        )

    if sold_units is not None and unsold_units is not None and absorption_pct is not None:
        score = 50.0 + absorption_pct * 0.45
        if launch_date:
            anchor = dld_signal.get("anchor_date") if dld_signal else None
            anchor_date = anchor if isinstance(anchor, date) else date.today()
            days_since_launch = max((anchor_date - launch_date).days, 0)
            if days_since_launch <= 90 and absorption_pct < 25:
                score += 8.0
            elif days_since_launch >= 365 and absorption_pct < 35:
                score -= 12.0
        score = _score_value(score)
        value = f"{sold_units:,} sold / {unsold_units:,} unsold"
        note = source or "Uses live inventory and registered-unit fallback."
    elif unsold_units is not None:
        if "out of stock" in sale_status and unsold_units == 0:
            score = 86.0
            value = "Sold out"
            note = "Sale status marks the project as out of stock."
        else:
            score = 68.0 if unsold_units > 0 else 62.0
            value = f"{unsold_units:,} unsold"
            note = source or "Live inventory count."
    else:
        score = 58.0
        value = f"{total_units:,} registered units" if total_units else "~"
        note = source or "Registered-unit fallback until live inventory is available."

    return _risk_indicator(
        key="sales",
        label="Sales absorption",
        value=value,
        score=score,
        note=note,
    )


def _developer_indicator(
    data: dict[str, Any], developer_scores: dict[str, DeveloperRankingResponse]
) -> SupplyCatalogueRiskIndicatorResponse:
    developer = developer_scores.get(_developer_logo_match_key(data.get("developer_name")))
    if developer is None or developer.proprietary_score is None:
        return _risk_indicator(
            key="developer",
            label="Developer overlay",
            value="~",
            score=None,
            available=False,
            note="Developer score match pending.",
        )
    return _risk_indicator(
        key="developer",
        label="Developer overlay",
        value=f"{developer.proprietary_score:.1f}",
        score=developer.proprietary_score,
        note=f"{developer.risk_badge} developer risk badge.",
    )


def _financial_risk_metrics() -> list[SupplyCatalogueFinancialMetricResponse]:
    return [
        SupplyCatalogueFinancialMetricResponse(
            key="escrow_balance",
            label="Escrow balance",
            value="~",
            status="Pending",
            note="Escrow feed pending.",
        ),
        SupplyCatalogueFinancialMetricResponse(
            key="adequacy_ratio",
            label="Adequacy ratio",
            value="~",
            status="Pending",
            note="Requires balance and required-minimum feed.",
        ),
        SupplyCatalogueFinancialMetricResponse(
            key="authorised_withdrawals",
            label="Authorised withdrawals",
            value="~",
            status="Pending",
            note="Withdrawal ledger pending.",
        ),
        SupplyCatalogueFinancialMetricResponse(
            key="remaining_construction_cost",
            label="Remaining construction cost",
            value="~",
            status="Pending",
            note="Cost-to-complete feed pending.",
        ),
        SupplyCatalogueFinancialMetricResponse(
            key="compliance_record",
            label="Compliance record",
            value="~",
            status="Pending",
            note="Violation and approval feed pending.",
        ),
    ]


async def _developer_logo_lookup(db: AsyncSession | None = None) -> dict[str, tuple[str, str]]:
    del db
    return {}


def _developer_identity(
    developer_name: str, logos: dict[str, tuple[str, str]]
) -> tuple[str, str | None]:
    key = _developer_logo_match_key(developer_name)
    if not key:
        return developer_name, None
    if key in logos:
        return logos[key]
    for logo_key, identity in logos.items():
        if len(logo_key) >= 4 and (logo_key in key or key in logo_key):
            return identity
    return developer_name, None


async def _latest_sales_date() -> date | None:
    rows = await query(
        """
        SELECT max(instance_date) AS max_date
        FROM ch_transactions
        WHERE trans_group_en = 'Sales'
          AND actual_worth > 0
        """,
        {},
    )
    if not rows:
        return None
    value = rows[0].get("max_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _developer_period(period: str, end_date: date) -> tuple[str, date, date]:
    normalized = period.lower().strip()
    label, days = DEVELOPER_RANKING_PERIODS.get(normalized, DEVELOPER_RANKING_PERIODS["1y"])
    if normalized == "ytd":
        return label, date(end_date.year, 1, 1), end_date
    return label, date.fromordinal(end_date.toordinal() - int(days or 365)), end_date


def _score_value(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed != parsed:
        return None
    return max(0.0, min(100.0, round(parsed, 1)))


def _ratio_score(numerator: Any, denominator: Any) -> float | None:
    denominator_value = float(denominator or 0)
    if denominator_value <= 0:
        return None
    return _score_value(float(numerator or 0) / denominator_value * 100)


def _unit_scale_score(value: Any, full_score_at: int) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed != parsed:
        return None
    if parsed <= 0:
        return 0.0
    return _score_value((parsed / full_score_at) ** 0.5 * 100)


def _risk_badge(score: float | None, coverage: float) -> str:
    if score is None or coverage < DEVELOPER_SCORE_MIN_WEIGHT:
        return "Review"
    if score >= 75:
        return "Low"
    if score >= 55:
        return "Medium"
    return "High"


def _developer_rank_sort_value(row: DeveloperRankingResponse, metric: str) -> float:
    values = {
        "proprietary_score": row.proprietary_score,
        "units_sold": row.units_sold,
        "sales_volume": row.sales_volume_aed,
        "avg_price_sqft": row.avg_price_sqft_aed,
        "pipeline_units": row.pipeline_units,
        "active_projects": row.active_projects,
        "completed_projects": row.completed_projects,
        "avg_completion_pct": row.avg_completion_pct,
    }
    value = values.get(metric)
    return float(value) if value is not None else -1.0


def _float_or_none(value: Any) -> float | None:
    return float(value) if value is not None else None


def _developer_criteria(
    row: dict[str, Any],
) -> tuple[list[DeveloperRankingCriterionResponse], float | None, float]:
    delivered_unit_score = _unit_scale_score(
        row.get("completed_units"), DEVELOPER_DELIVERED_UNIT_FULL_SCORE
    )
    pipeline_unit_score = _unit_scale_score(
        row.get("pipeline_units"), DEVELOPER_PIPELINE_UNIT_FULL_SCORE
    )
    on_time_score = _score_value(row.get("on_time_delivery_score"))
    if on_time_score is None:
        on_time_score = _ratio_score(
            row.get("on_time_units"), row.get("completed_units_with_schedule")
        )
    definitions = [
        (
            "delivered_unit_scale",
            "Delivered unit scale",
            delivered_unit_score,
            "Completed registered units, scored with diminishing returns for proven scale.",
        ),
        (
            "pipeline_unit_scale",
            "Pipeline unit scale",
            pipeline_unit_score,
            "Active registered pipeline units, scored with diminishing returns for current depth.",
        ),
        (
            "on_time_delivery",
            "On-time delivery",
            on_time_score,
            "Completed projects delivered on or before declared end date, weighted by units.",
        ),
    ]

    criteria: list[DeveloperRankingCriterionResponse] = []
    available_weight = 0.0
    weighted_score = 0.0
    for key, label, score, note in definitions:
        weight = DEVELOPER_SCORE_WEIGHTS[key]
        available = score is not None
        if available:
            available_weight += weight
            weighted_score += score * weight
        criteria.append(
            DeveloperRankingCriterionResponse(
                key=key,
                label=label,
                weight_pct=weight,
                score=score,
                available=available,
                note=note,
            )
        )

    proprietary_score = (
        round(weighted_score / available_weight, 1)
        if available_weight >= DEVELOPER_SCORE_MIN_WEIGHT
        else None
    )
    return criteria, proprietary_score, round(available_weight, 1)


async def get_developer_rankings(
    db: AsyncSession | None = None,
    period: str = "1y",
    metric: str = "proprietary_score",
    limit: int = 25,
) -> DeveloperRankingsResponse:
    ranking_metric = metric if metric in DEVELOPER_RANKING_METRICS else "proprietary_score"
    end_date = await _latest_sales_date() or date.today()
    period_label, start_date, end_date = _developer_period(period, end_date)
    logos = await _developer_logo_lookup(db)

    rows = await query(
        """
        SELECT
            max(pf.developer_id) AS developer_id,
            any(pf.developer_name) AS developer_name,
            sum(pf.sales_transaction_count_12m) AS units_sold,
            sum(pf.sales_transaction_count_12m) AS sales_transaction_count,
            sum(pf.total_sales_volume_12m) AS sales_volume_aed,
            if(
                sum(pf.sales_transaction_count_12m) > 0,
                sum(pf.avg_sale_price_sqm_12m * pf.sales_transaction_count_12m)
                    / sum(pf.sales_transaction_count_12m) / {sqm_to_sqft:Float64},
                NULL
            ) AS avg_price_sqft_aed,
            countIf(pf.sales_transaction_count_12m > 0) AS selling_projects,
            count() AS total_projects,
            countIf(pf.completion_date IS NULL AND pf.cancellation_date IS NULL) AS active_projects,
            countIf(pf.completion_date IS NOT NULL) AS completed_projects,
            sumIf(pf.no_of_units, pf.completion_date IS NOT NULL) AS completed_units,
            sumIf(pf.no_of_units, pf.completion_date IS NULL AND pf.cancellation_date IS NULL) AS pipeline_units,
            sum(pf.no_of_units) AS registered_units,
            avgIf(pf.percent_completed, pf.completion_date IS NULL AND pf.cancellation_date IS NULL) AS avg_completion_pct,
            sumIf(
                pf.no_of_units,
                pf.completion_date IS NOT NULL
                AND pf.project_end_date IS NOT NULL
                AND pf.completion_date <= pf.project_end_date
            ) AS on_time_units,
            sumIf(
                pf.no_of_units,
                pf.completion_date IS NOT NULL AND pf.project_end_date IS NOT NULL
            ) AS completed_units_with_schedule,
            countIf(pf.project_start_date >= subtractYears({end_date:Date}, 10)) AS initiated_projects_10y,
            countIf(
                pf.project_start_date >= subtractYears({end_date:Date}, 10)
                AND pf.completion_date IS NOT NULL
            ) AS completed_projects_10y,
            if(
                completed_units_with_schedule > 0,
                on_time_units / completed_units_with_schedule * 100,
                NULL
            ) AS on_time_delivery_score,
            if(registered_units > 0, least(100, units_sold / registered_units * 100), NULL)
                AS sales_completion_score,
            if(
                initiated_projects_10y > 0,
                completed_projects_10y / initiated_projects_10y * 100,
                NULL
            ) AS historical_project_success_score
        FROM ch_project_fact AS pf
        WHERE pf.developer_name != ''
        GROUP BY lowerUTF8(pf.developer_name)
        """,
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "sqm_to_sqft": SQM_TO_SQFT,
        },
    )

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        brand_name = _developer_brand_name(str(row.get("developer_name") or ""))
        developer_name, logo_url = _developer_identity(brand_name, logos)
        if _developer_ranking_hidden(developer_name):
            continue
        if not _developer_rankable_brand(developer_name):
            continue
        group_key = _developer_logo_match_key(developer_name) or developer_name.lower()
        group = grouped.setdefault(
            group_key,
            {
                "developer_name": developer_name,
                "developer_id": row.get("developer_id"),
                "developer_logo_url": logo_url,
                "units_sold": 0,
                "sales_transaction_count": 0,
                "sales_volume_aed": 0.0,
                "avg_price_sqft_weighted": 0.0,
                "avg_price_sqft_weight": 0,
                "selling_projects": 0,
                "total_projects": 0,
                "active_projects": 0,
                "completed_projects": 0,
                "completed_units": 0,
                "pipeline_units": 0,
                "registered_units": 0,
                "avg_completion_weighted": 0.0,
                "avg_completion_weight": 0,
                "on_time_units": 0,
                "completed_units_with_schedule": 0,
                "initiated_projects_10y": 0,
                "completed_projects_10y": 0,
            },
        )
        group["units_sold"] += int(row.get("units_sold") or 0)
        group["sales_transaction_count"] += int(row.get("sales_transaction_count") or 0)
        group["sales_volume_aed"] += float(row.get("sales_volume_aed") or 0)
        group["selling_projects"] += int(row.get("selling_projects") or 0)
        group["total_projects"] += int(row.get("total_projects") or 0)
        group["active_projects"] += int(row.get("active_projects") or 0)
        group["completed_projects"] += int(row.get("completed_projects") or 0)
        group["completed_units"] += int(row.get("completed_units") or 0)
        group["pipeline_units"] += int(row.get("pipeline_units") or 0)
        group["registered_units"] += int(row.get("registered_units") or 0)
        group["on_time_units"] += int(row.get("on_time_units") or 0)
        group["completed_units_with_schedule"] += int(row.get("completed_units_with_schedule") or 0)
        group["initiated_projects_10y"] += int(row.get("initiated_projects_10y") or 0)
        group["completed_projects_10y"] += int(row.get("completed_projects_10y") or 0)

        sales_count = int(row.get("sales_transaction_count") or 0)
        avg_price_sqft = _float_or_none(row.get("avg_price_sqft_aed"))
        if avg_price_sqft is not None and sales_count:
            group["avg_price_sqft_weighted"] += avg_price_sqft * sales_count
            group["avg_price_sqft_weight"] += sales_count

        active_projects = int(row.get("active_projects") or 0)
        avg_completion = _float_or_none(row.get("avg_completion_pct"))
        if avg_completion is not None and active_projects:
            group["avg_completion_weighted"] += avg_completion * active_projects
            group["avg_completion_weight"] += active_projects

    rankings: list[DeveloperRankingResponse] = []
    for row in grouped.values():
        row["avg_price_sqft_aed"] = (
            row["avg_price_sqft_weighted"] / row["avg_price_sqft_weight"]
            if row["avg_price_sqft_weight"]
            else None
        )
        row["avg_completion_pct"] = (
            row["avg_completion_weighted"] / row["avg_completion_weight"]
            if row["avg_completion_weight"]
            else None
        )
        row["on_time_delivery_score"] = _ratio_score(
            row.get("on_time_units"), row.get("completed_units_with_schedule")
        )
        row["sales_completion_score"] = _ratio_score(
            row.get("units_sold"), row.get("registered_units")
        )
        row["historical_project_success_score"] = _ratio_score(
            row.get("completed_projects_10y"), row.get("initiated_projects_10y")
        )
        criteria, proprietary_score, coverage = _developer_criteria(row)
        ranking = DeveloperRankingResponse(
            rank=0,
            developer_name=str(row.get("developer_name") or "Unknown developer"),
            developer_id=int(row["developer_id"]) if row.get("developer_id") is not None else None,
            developer_logo_url=row.get("developer_logo_url"),
            proprietary_score=proprietary_score,
            score_coverage_pct=coverage,
            risk_badge=_risk_badge(proprietary_score, coverage),
            units_sold=int(row.get("units_sold") or 0),
            sales_transaction_count=int(row.get("sales_transaction_count") or 0),
            sales_volume_aed=float(row.get("sales_volume_aed") or 0),
            avg_price_sqft_aed=float(row["avg_price_sqft_aed"])
            if row.get("avg_price_sqft_aed") is not None
            else None,
            selling_projects=int(row.get("selling_projects") or 0),
            total_projects=int(row.get("total_projects") or 0),
            active_projects=int(row.get("active_projects") or 0),
            completed_projects=int(row.get("completed_projects") or 0),
            pipeline_units=int(row.get("pipeline_units") or 0),
            registered_units=int(row.get("registered_units") or 0),
            avg_completion_pct=float(row["avg_completion_pct"])
            if row.get("avg_completion_pct") is not None
            else None,
            on_time_delivery_score=_score_value(row.get("on_time_delivery_score")),
            sales_completion_score=_score_value(row.get("sales_completion_score")),
            historical_project_success_score=_score_value(
                row.get("historical_project_success_score")
            ),
            criteria=criteria,
        )
        rankings.append(ranking)

    if ranking_metric == "proprietary_score":
        rankings = [ranking for ranking in rankings if ranking.proprietary_score is not None]
    else:
        rankings = [
            ranking
            for ranking in rankings
            if _developer_rank_sort_value(ranking, ranking_metric) > 0
        ]

    rankings.sort(
        key=lambda item: (
            -_developer_rank_sort_value(item, ranking_metric),
            -item.sales_volume_aed,
            item.developer_name.lower(),
        )
    )
    rankings = rankings[:limit]
    for index, ranking in enumerate(rankings, start=1):
        ranking.rank = index

    return DeveloperRankingsResponse(
        rankings=rankings,
        summary=DeveloperRankingSummaryResponse(
            total_developers=len(grouped),
            period_label=period_label,
            start_date=start_date,
            end_date=end_date,
            ranking_metric=ranking_metric,
            available_score_weight_pct=sum(DEVELOPER_SCORE_WEIGHTS.values()),
            unavailable_criteria=[],
        ),
    )


async def _developer_score_lookup(
    db: AsyncSession | None = None,
) -> dict[str, DeveloperRankingResponse]:
    del db
    return {}


def _project_match_score(catalogue: dict[str, Any], dld_project: dict[str, Any]) -> float:
    project_score = _token_overlap(catalogue.get("project_name"), dld_project.get("project_name"))
    developer_score = _token_overlap(
        catalogue.get("developer_name"), dld_project.get("developer_name")
    )
    area_score = (
        1.0
        if _developer_logo_match_key(catalogue.get("area_name"))
        == _developer_logo_match_key(dld_project.get("area_name"))
        else _token_overlap(catalogue.get("area_name"), dld_project.get("area_name"))
    )
    return project_score * 0.6 + developer_score * 0.25 + area_score * 0.15


async def _dld_project_signal_lookup(
    catalogue_rows: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    if not catalogue_rows:
        return {}
    area_keys = sorted(
        {
            str(row.get("area_name") or "").strip().lower()
            for row in catalogue_rows
            if row.get("area_name")
        }
    )
    try:
        anchor_date = await _latest_sales_date() or date.today()
        rows = await query(
            """
            SELECT
                p.project_id AS project_id,
                p.project_name_en AS project_name,
                coalesce(nullIf(d.developer_name_en, ''), nullIf(p.developer_name, '')) AS developer_name,
                p.area_name_en AS area_name,
                p.project_start_date AS project_start_date,
                coalesce(p.completion_date, p.project_end_date) AS project_end_date,
                p.percent_completed AS percent_completed,
                p.no_of_units AS no_of_units
            FROM ch_projects p
            LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
            WHERE p.project_name_en != ''
              AND (
                    {area_count:Int32} = 0
                    OR has({areas:Array(String)}, lowerUTF8(coalesce(p.area_name_en, '')))
                  )
            LIMIT 5000
            """,
            {"area_count": len(area_keys), "areas": area_keys},
        )
    except Exception as exc:
        logger.warning("DLD project signal lookup failed for supply catalogue: %s", exc)
        return {}

    matches: dict[int, dict[str, Any]] = {}
    for catalogue in catalogue_rows:
        best_score = 0.0
        best_row: dict[str, Any] | None = None
        for candidate in rows:
            score = _project_match_score(catalogue, candidate)
            if score > best_score:
                best_score = score
                best_row = candidate
        if best_row and best_score >= 0.42:
            matches[int(catalogue["project_id"])] = {
                **best_row,
                "match_score": round(best_score, 2),
                "anchor_date": anchor_date,
            }
    return matches


def _catalogue_today_ms() -> int:
    today_start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
    return int(today_start.timestamp() * 1000)


def _catalogue_ch_filters(
    search: str | None,
    area: str | None,
    status: str | None,
    developer: str | None = None,
    include_past: bool = False,
) -> tuple[str, dict[str, Any]]:
    clauses = [
        reelly_dubai_project_scope(),
        "JSON_VALUE(list_item_json, '$.Project_name') != ''",
    ]
    params: dict[str, Any] = {}
    if not include_past:
        clauses.append(
            """
            (
                toInt64OrNull(JSON_VALUE(list_item_json, '$.Completion_time')) IS NULL
                OR toInt64OrNull(JSON_VALUE(list_item_json, '$.Completion_time')) >= {today_ms:Int64}
            )
            """
        )
        params["today_ms"] = _catalogue_today_ms()
    if search:
        clauses.append(
            """
            (
                positionCaseInsensitive(JSON_VALUE(list_item_json, '$.Project_name'), {search:String}) > 0
                OR positionCaseInsensitive(JSON_VALUE(list_item_json, '$.Developers_name'), {search:String}) > 0
                OR positionCaseInsensitive(JSON_VALUE(list_item_json, '$.Area_name'), {search:String}) > 0
            )
            """
        )
        params["search"] = search
    if area:
        clauses.append("JSON_VALUE(list_item_json, '$.Area_name') = {area:String}")
        params["area"] = area
    if status:
        clauses.append("JSON_VALUE(list_item_json, '$.Status') = {status:String}")
        params["status"] = status
    if developer:
        clauses.append(
            "positionCaseInsensitive(JSON_VALUE(list_item_json, '$.Developers_name'), {developer:String}) > 0"
        )
        params["developer"] = developer
    return " AND ".join(clauses), params


def _catalogue_ch_order_by(sort: str) -> str:
    normalized = sort if sort in SUPPLY_CATALOGUE_SORTS else "recommended"
    min_price = "nullIf(toInt64OrNull(JSON_VALUE(list_item_json, '$.min_price')), 0)"
    completion_time = "toInt64OrNull(JSON_VALUE(list_item_json, '$.Completion_time'))"
    if normalized == "newest":
        return "parseDateTimeBestEffortOrNull(scraped_at) DESC NULLS LAST, toInt64OrNull(project_key) DESC"
    if normalized == "price_low":
        return f"{min_price} ASC NULLS LAST, JSON_VALUE(list_item_json, '$.Project_name') ASC"
    if normalized == "price_high":
        return f"{min_price} DESC NULLS LAST, JSON_VALUE(list_item_json, '$.Project_name') ASC"
    if normalized == "delivery_soon":
        return f"{completion_time} ASC NULLS LAST, JSON_VALUE(list_item_json, '$.Project_name') ASC"
    if normalized == "delivery_latest":
        return (
            f"{completion_time} DESC NULLS LAST, JSON_VALUE(list_item_json, '$.Project_name') ASC"
        )
    return f"""
        multiIf(
            JSON_VALUE(list_item_json, '$.sale_status') = 'On sale', 0,
            positionCaseInsensitive(JSON_VALUE(list_item_json, '$.sale_status'), 'presale') > 0, 1,
            2
        ) ASC,
        {min_price} ASC NULLS LAST,
        JSON_VALUE(list_item_json, '$.Project_name') ASC
    """


async def _catalogue_facet_values(
    field_path: str,
    filters: tuple[str, dict[str, Any]],
    limit: int,
) -> list[str]:
    where, params = filters
    rows = await query(
        f"""
        SELECT JSON_VALUE(list_item_json, '$.{field_path}') AS value, count() AS n
        FROM reelly_projects_bronze
        WHERE {where}
          AND JSON_VALUE(list_item_json, '$.{field_path}') != ''
        GROUP BY value
        ORDER BY n DESC, value ASC
        LIMIT {{limit:Int32}}
        """,
        {**params, "limit": limit},
    )
    return [str(row["value"]) for row in rows if row.get("value")]


async def list_supply_catalogue_projects(
    db: AsyncSession | None = None,
    limit: int = 48,
    offset: int = 0,
    search: str | None = None,
    area: str | None = None,
    status: str | None = None,
    developer: str | None = None,
    sort: str = "recommended",
    include_past: bool = False,
) -> SupplyCatalogueProjectsResponse:
    del db
    where, params = _catalogue_ch_filters(search, area, status, developer, include_past)
    rows = await query(
        f"""
        SELECT project_key, project_id, run_id, scraped_at, list_item_json, raw_json
        FROM reelly_projects_bronze
        WHERE {where}
        ORDER BY {_catalogue_ch_order_by(sort)}
        LIMIT {{limit:Int32}} OFFSET {{offset:Int32}}
        """,
        {**params, "limit": limit, "offset": offset},
    )
    count_rows = await query(
        f"""
        SELECT count() AS total
        FROM reelly_projects_bronze
        WHERE {where}
        """,
        params,
    )
    row_data = [_catalogue_data_from_clickhouse_row(row) for row in rows]
    developer_scores = await _developer_score_lookup()
    dld_signals = await _dld_project_signal_lookup(row_data)
    projects = [_card_from_row(row, developer_scores, dld_signals) for row in row_data]
    base_filters = _catalogue_ch_filters(None, None, None, None, include_past)
    developer_filters = _catalogue_ch_filters(search, area, status, None, include_past)
    return SupplyCatalogueProjectsResponse(
        projects=projects,
        total=int(count_rows[0]["total"]) if count_rows else 0,
        limit=limit,
        offset=offset,
        areas=await _catalogue_facet_values("Area_name", base_filters, 40),
        statuses=await _catalogue_facet_values("Status", base_filters, 20),
        developers=await _catalogue_facet_values("Developers_name", developer_filters, 120),
    )


async def get_supply_catalogue_project(
    db: AsyncSession | None, project_id: int
) -> SupplyCatalogueProjectDetailResponse:
    del db
    rows = await query(
        f"""
        SELECT project_key, project_id, run_id, scraped_at, list_item_json, raw_json
        FROM reelly_projects_bronze
        WHERE (project_key = {{project_id:String}} OR project_id = {{project_id:String}})
          AND {reelly_dubai_project_scope()}
        LIMIT 1
        """,
        {"project_id": str(project_id)},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Supply catalogue project not found")

    data = _catalogue_data_from_clickhouse_row(rows[0])
    developer_scores = await _developer_score_lookup()
    dld_signals = await _dld_project_signal_lookup([data])
    card = _card_from_row(data, developer_scores, dld_signals)
    scraped_at = data.get("scraped_at")

    return SupplyCatalogueProjectDetailResponse(
        **card.model_dump(),
        overview=data.get("overview"),
        coordinates=data.get("coordinates"),
        units=[
            SupplyCatalogueUnitResponse.model_validate(item) for item in _as_list(data.get("units"))
        ],
        payment_plan=[
            SupplyCataloguePaymentStepResponse.model_validate(item)
            for item in _as_list(data.get("payment_plan"))
        ],
        facilities=[str(item) for item in _as_list(data.get("facilities")) if item],
        buildings=[
            SupplyCatalogueBuildingResponse.model_validate(item)
            for item in _as_list(data.get("buildings"))
        ],
        nearby_points=[
            SupplyCatalogueNearbyPointResponse.model_validate(item)
            for item in _as_list(data.get("nearby_points"))
        ],
        gallery=data.get("gallery", [])[:18],
        floorplans=data.get("floorplans", [])[:12],
        brochures=data.get("brochures", [])[:6],
        master_plans=data.get("master_plans", [])[:4],
        source_metadata={
            "source": "ph_box ClickHouse reelly_projects_bronze",
            "source_run_id": data.get("source_run_id"),
            "scraped_at": scraped_at.isoformat()
            if isinstance(scraped_at, datetime)
            else (_text_or_none(scraped_at)),
        },
        financial_risk_metrics=_financial_risk_metrics(),
        estimated_project_irr="~",
    )
