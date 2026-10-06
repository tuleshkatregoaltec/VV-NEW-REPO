"""ClickHouse-backed lead inference for lease expiry opportunities."""

import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.clickhouse.client import query
from app.crm.models import (
    CrmAssetBreakdownItem,
    CrmBreakdownItem,
    CrmCoverage,
    CrmDashboardResponse,
    CrmFilters,
    CrmLead,
    CrmLeadDetailResponse,
    CrmLeadNote,
    CrmLeadNoteResponse,
    CrmLeadWorkspace,
    CrmNoteCreate,
    CrmPriceIndex,
    CrmPriceIndexPoint,
    CrmPropertyReportResponse,
    CrmRentalComparable,
    CrmReportAnalysis,
    CrmSaleComparable,
    CrmSavedLead,
    CrmSavedLeadResponse,
    CrmSummary,
    CrmTimelineEvent,
    CrmWorkspaceResponse,
    CrmWorkspaceSummary,
    CrmWorkspaceUpdate,
)

logger = logging.getLogger(__name__)

DXBI_TABLE = "dxbi_rental_events"
DXBI_CANDIDATE_TABLE = "dxbi_rental_unit_candidates"
_LEGACY_RENTAL_TABLES = (
    "dxbi_rental_events",
    "dxbi_rental_unit_candidates",
    "dxbi_rental_sale_matches",
)
VALID_BREAKDOWNS = {
    "area": "area_name",
    "project": "project_name",
    "building": "building_name",
}


async def _query_with_legacy_rentals(
    sql: str, params: dict[str, Any], *, saved_candidates: bool = False
) -> list[dict[str, Any]]:
    """Keep saved v1 identities readable without guessing a replacement v2 unit."""
    rows = await query(sql, params)
    legacy_params = dict(params)
    if saved_candidates:
        found = {str(row["saved_candidate_key"]) for row in rows}
        missing = [key for key in params["candidate_keys"] if key not in found]
        if not missing:
            return rows
        legacy_params["candidate_keys"] = missing
    elif rows:
        return rows
    required = [name for name in _LEGACY_RENTAL_TABLES if name in sql]
    available = await query(
        "SELECT count() AS tables FROM system.tables "
        "WHERE database=currentDatabase() AND name IN {names:Array(String)}",
        {"names": [name + "_legacy" for name in required]},
    )
    if not required or not available or int(available[0]["tables"]) != len(required):
        return rows
    legacy_sql = sql
    for name in required:
        legacy_sql = legacy_sql.replace(name, name + "_legacy")
    legacy_rows = await query(legacy_sql, legacy_params)
    return [*rows, *[{**row, "_legacy_identity": True} for row in legacy_rows]]


_LEAD_CTE = """
WITH coverage AS (
    SELECT max(source_shard_date) AS data_complete_through
    FROM dxbi_rental_events FINAL
),
latest_unit AS (
    SELECT
        c.event_key,
        c.unit_candidate_key AS unit_candidate_key,
        c.unit_cohort_key,
        c.location_name,
        if(
            c.property_type IN ('Villa', 'Townhouse'),
            '',
            coalesce(nullIf(g.display_building_name, ''), c.building_name)
        ) AS building_name,
        coalesce(nullIf(g.display_project_name, ''), c.project_name) AS project_name,
        coalesce(nullIf(g.display_area_name, ''), c.area_name) AS area_name,
        c.building_name AS registry_building_name,
        c.project_name AS registry_project_name,
        c.area_name AS registry_area_name,
        g.canonical_location_id,
        coalesce(nullIf(g.match_status, ''), 'unmapped') AS geography_match_status,
        coalesce(nullIf(g.coordinate_precision, ''), 'missing') AS coordinate_precision,
        g.latitude,
        g.longitude,
        c.property_type,
        c.bedrooms,
        c.size_sqft,
        c.contract_amount_aed,
        c.contract_term_days,
        c.contract_term_months,
        c.annual_rent_aed,
        c.rent_normalization_version,
        c.address_normalization_version,
        c.purchase_price_aed,
        c.lease_start,
        c.lease_end,
        c.contract_state,
        c.observed_contracts,
        c.last_scraped_at,
        c.loaded_at,
        coalesce(nullIf(c.unit_number, ''), m.unit_number) AS unit_number,
        m.identity_sale_date,
        m.identity_sale_price,
        m.last_purchase_date,
        m.matched_sale_price,
        m.latest_property_type,
        m.latest_price_per_sqft_aed,
        m.latest_capital_gain_pct,
        m.latest_ltv_pct,
        m.latest_seller_type,
        m.latest_seller_transaction_count,
        m.latest_market_status,
        m.latest_detail_url,
        m.matching_units,
        m.match_status AS unit_match_status
    FROM dxbi_rental_unit_candidates AS c FINAL
    LEFT JOIN geo_crm_rental_hierarchy AS g
        ON g.registry_area_name = c.area_name
        AND g.registry_project_name = c.project_name
        AND g.registry_building_name = c.building_name
        AND g.source_grain = multiIf(
            c.property_type IN ('Villa', 'Townhouse'), 'landed_phase',
            c.building_name != '', 'building',
            c.project_name != '', 'project',
            'area'
        )
    LEFT JOIN dxbi_rental_sale_matches AS m FINAL
        ON m.unit_candidate_key = c.unit_candidate_key
),
identified_unit AS (
    SELECT
        *,
        if(
            unit_match_status = 'unique' AND ifNull(unit_number, '') != '',
            concat(
                'unit:',
                replaceRegexpAll(
                    lowerUTF8(coalesce(nullIf(building_name, ''), nullIf(project_name, ''), location_name)),
                    '[^a-z0-9]+',
                    ''
                ),
                ':',
                replaceRegexpAll(lowerUTF8(area_name), '[^a-z0-9]+', ''),
                ':',
                upperUTF8(unit_number)
            ),
            concat('candidate:', unit_candidate_key)
        ) AS property_identity_key
    FROM latest_unit
),
ranked_unit AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY property_identity_key
            ORDER BY lease_start DESC, lease_end DESC, last_scraped_at DESC, event_key DESC
        ) AS identity_rank
    FROM identified_unit
),
lead_evidence AS (
    SELECT
        r.*,
        c.data_complete_through,
        multiIf(
            property_type IN ('Apartment', 'Villa'), 'residential',
            property_type = 'Commercial', 'commercial',
            'other'
        ) AS asset_class,
        multiIf(
            property_type = 'Commercial'
                AND latest_property_type IN (
                    'Office',
                    'Shop',
                    'Warehouse',
                    'Show Rooms',
                    'Workshop',
                    'Clinic',
                    'Gymnasium',
                    'Hotel'
                ),
            latest_property_type,
            property_type != '',
            property_type,
            'Other'
        ) AS property_subtype,
        dateDiff('day', {as_of:Date}, lease_end) AS days_to_expiry,
        multiIf(
            unit_match_status != 'unique', 'unit_unresolved',
            last_purchase_date >= lease_start
                AND last_purchase_date < lease_end,
                'sale_during_lease',
            'stable_rental_history'
        ) AS ownership_timing,
        multiIf(
            lease_end >= {as_of:Date}, 'upcoming',
            unit_match_status != 'unique', 'unit_unresolved',
            last_purchase_date >= lease_start
                AND last_purchase_date < lease_end,
                'ownership_review',
            'unlet_signal'
        ) AS lease_evidence_state,
        multiIf(
            lease_end < {as_of:Date}, 'expired',
            lease_end <= addDays({as_of:Date}, 30), 'expiring_30',
            lease_end <= addDays({as_of:Date}, 60), 'expiring_60',
            'expiring_90'
        ) AS lead_status,
        if(
            unit_match_status = 'unique',
            'high',
            if(purchase_price_aed > 0, 'medium', 'low')
        )
            AS match_confidence
    FROM ranked_unit AS r
    CROSS JOIN coverage AS c
    WHERE
        identity_rank = 1
        AND
        lease_end >= addDays({as_of:Date}, -{expired_days:Int32})
        AND lease_end <= addDays({as_of:Date}, 90)
        AND NOT (
            unit_match_status = 'unique'
            AND last_purchase_date >= lease_end
        )
),
leads AS (
    SELECT
        *,
        greatest(
            0,
            least(
                100,
                multiIf(
                    lead_status = 'expired' AND lease_evidence_state = 'unlet_signal', 88,
                    lead_status = 'expiring_30', 84,
                    lead_status = 'expiring_60', 72,
                    60
                )
                + if(unit_match_status = 'unique', 6, 0)
                + if(contract_state = 'Renewed', 2, 0)
                - if(ownership_timing = 'sale_during_lease', 25, 0)
            )
        ) AS raw_score,
        if(raw_score >= 90, 'urgent', if(raw_score >= 75, 'high', 'medium')) AS priority
    FROM lead_evidence
)
"""


def _where_clause(
    *,
    status: str | None,
    priority: str | None,
    area: str | None,
    project: str | None,
    building: str | None,
    search: str | None,
    asset_class: str | None = None,
    property_type: str | None = None,
) -> tuple[str, dict[str, Any]]:
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    if status:
        conditions.append("lead_status = {status:String}")
        params["status"] = status
    if priority:
        conditions.append("priority = {priority:String}")
        params["priority"] = priority
    if area:
        conditions.append("area_name = {area:String}")
        params["area"] = area
    if project:
        conditions.append("project_name = {project:String}")
        params["project"] = project
    if building:
        conditions.append("building_name = {building:String}")
        params["building"] = building
    if asset_class:
        conditions.append("asset_class = {asset_class:String}")
        params["asset_class"] = asset_class
    if property_type:
        conditions.append("property_subtype = {property_type:String}")
        params["property_type"] = property_type
    if search:
        conditions.append(
            """
            positionCaseInsensitiveUTF8(
                concat(
                    building_name,
                    ' ',
                    project_name,
                    ' ',
                    area_name,
                    ' ',
                    bedrooms,
                    ' ',
                    property_subtype,
                    ' ',
                    ifNull(unit_number, '')
                ),
                {search:String}
            ) > 0
            """
        )
        params["search"] = search
    return " AND ".join(conditions), params


def _filter_metadata_sql(facet_where: str) -> str:
    """Return live lead facets so every dropdown option can produce a result."""
    return (
        _LEAD_CTE
        + f"""
        SELECT
            (SELECT count() FROM dxbi_rental_events FINAL) AS rows,
            (
                SELECT countIf(match_status = 'unique')
                FROM dxbi_rental_sale_matches FINAL
            ) AS exact_unit_matches,
            min(lease_start) AS min_date,
            max(lease_start) AS max_date,
            (SELECT max(source_shard_date) FROM dxbi_rental_events FINAL)
                AS data_complete_through,
            arraySort(groupUniqArrayIf(area_name, area_name != '')) AS areas,
            arraySort(
                groupUniqArrayIf(
                    project_name,
                    project_name != ''
                    AND {{filter_area:String}} != ''
                    AND area_name = {{filter_area:String}}
                )
            ) AS projects,
            arraySort(
                groupUniqArrayIf(
                    building_name,
                    building_name != ''
                    AND {{filter_area:String}} != ''
                    AND area_name = {{filter_area:String}}
                    AND {{filter_project:String}} != ''
                    AND project_name = {{filter_project:String}}
                )
            ) AS buildings
        FROM leads
        WHERE {facet_where}
        """
    )


def _lead_from_row(row: dict[str, Any]) -> CrmLead:
    # Saved-lead joins return l.* fields with the table alias in their names.
    row = {key.removeprefix("l."): value for key, value in row.items()}
    days = int(row["days_to_expiry"])
    status = str(row["lead_status"])
    expired = status == "expired"
    asset_class = str(row.get("asset_class") or "other")
    property_type = str(row.get("property_type") or "Property")
    matched_sales_property_type = str(row.get("latest_property_type") or "").strip() or None
    property_subtype = str(row.get("property_subtype") or property_type)
    unit_number = str(row.get("unit_number") or "").strip() or None
    unit_resolved = bool(unit_number and row.get("unit_match_status") == "unique")
    ownership_timing = str(
        row.get("ownership_timing")
        or ("stable_rental_history" if unit_resolved else "unit_unresolved")
    )
    lease_evidence_state = str(
        row.get("lease_evidence_state")
        or (
            "ownership_review"
            if ownership_timing == "sale_during_lease"
            else "unlet_signal"
            if expired and unit_resolved
            else "unit_unresolved"
            if expired
            else "upcoming"
        )
    )
    sale_candidate = bool(
        unit_resolved
        and expired
        and lease_evidence_state == "unlet_signal"
        and ownership_timing == "stable_rental_history"
    )
    matched_sale_price = int(row.get("matched_sale_price") or 0) or None
    annual_rent = int(row.get("annual_rent_aed") or 0)
    gross_yield = (
        round(annual_rent / matched_sale_price * 100, 2)
        if matched_sale_price and annual_rent
        else None
    )
    if ownership_timing == "sale_during_lease":
        reason = (
            "Ownership changed during the lease and no post-purchase lease is yet linked to "
            "this exact unit. Occupancy requires verification."
        )
    elif expired:
        reason = (
            f"Unlet signal: lease expired {abs(days)} days ago and no later registered lease "
            "was observed for this exact unit."
            if unit_resolved
            else f"Lease candidate expired {abs(days)} days ago; exact-unit and renewal status "
            "remain unresolved."
        )
    else:
        reason = f"Lease expires in {days} days; begin a renewal-status conversation."
    if ownership_timing == "sale_during_lease":
        action = "Verify the current owner and occupancy before proposing renewal or re-letting."
    elif asset_class == "commercial" and unit_resolved and expired and sale_candidate:
        action = (
            f"Use unit {unit_number} to resolve the current owner, then offer a leasing "
            "mandate and test appetite for an investment sale."
        )
    elif asset_class == "commercial" and unit_resolved:
        action = (
            f"Use unit {unit_number} to resolve the current owner, then open a renewal "
            "or commercial leasing conversation."
        )
    elif asset_class == "commercial" and expired and sale_candidate:
        action = (
            "Resolve the exact unit, then offer a commercial leasing mandate and test "
            "appetite for an investment sale."
        )
    elif asset_class == "commercial":
        action = (
            "Resolve the exact unit, then contact the owner about renewal or commercial re-letting."
        )
    elif unit_resolved and expired and sale_candidate:
        action = (
            f"Use unit {unit_number} to resolve the current owner, then offer re-letting "
            "and test appetite for a sale."
        )
    elif unit_resolved:
        action = (
            f"Use unit {unit_number} to resolve the current owner, then open a renewal "
            "or re-letting conversation."
        )
    elif expired and sale_candidate:
        action = "Resolve the exact unit, then offer re-letting and test appetite for a sale."
    else:
        action = "Resolve the exact unit, then contact the owner about renewal or re-letting."
    if row.get("_legacy_identity"):
        reason = (
            "Saved rental snapshot from before the data refresh; current lease status needs review."
        )
        action = "Check the current unit and lease evidence before contacting the owner."
    return CrmLead(
        lead_id=str(row["event_key"]),
        unit_candidate_key=str(row["unit_candidate_key"]),
        building_name=str(row.get("building_name") or ""),
        project_name=str(row.get("project_name") or ""),
        area_name=str(row.get("area_name") or ""),
        registry_building_name=str(row.get("registry_building_name") or ""),
        registry_project_name=str(row.get("registry_project_name") or ""),
        registry_area_name=str(row.get("registry_area_name") or ""),
        canonical_location_id=str(row.get("canonical_location_id") or "") or None,
        geography_match_status=str(row.get("geography_match_status") or "unmapped"),
        coordinate_precision=str(row.get("coordinate_precision") or "missing"),
        latitude=float(row["latitude"]) if row.get("latitude") is not None else None,
        longitude=float(row["longitude"]) if row.get("longitude") is not None else None,
        asset_class=asset_class,
        property_type=property_type,
        property_subtype=property_subtype,
        matched_sales_property_type=matched_sales_property_type,
        bedrooms=str(row.get("bedrooms") or "Not stated"),
        size_sqft=float(row["size_sqft"]) if row.get("size_sqft") else None,
        contract_amount_aed=int(row.get("contract_amount_aed") or row.get("annual_rent_aed") or 0),
        contract_term_days=int(
            row.get("contract_term_days") or ((row["lease_end"] - row["lease_start"]).days + 1)
        ),
        contract_term_months=(
            float(row["contract_term_months"]) if row.get("contract_term_months") else None
        ),
        annual_rent_aed=annual_rent,
        latest_purchase_price_aed=(
            int(row["purchase_price_aed"]) if row.get("purchase_price_aed") else None
        ),
        unit_number=unit_number,
        unit_match_status=str(row.get("unit_match_status") or "unresolved"),
        matching_units=int(row.get("matching_units") or 0),
        last_purchase_date=row.get("last_purchase_date"),
        matched_sale_price_aed=matched_sale_price,
        gross_yield_pct=gross_yield,
        identity_sale_date=row.get("identity_sale_date"),
        identity_sale_price_aed=(
            int(row["identity_sale_price"]) if row.get("identity_sale_price") else None
        ),
        latest_price_per_sqft_aed=(
            float(row["latest_price_per_sqft_aed"])
            if row.get("latest_price_per_sqft_aed") is not None
            else None
        ),
        latest_capital_gain_pct=(
            float(row["latest_capital_gain_pct"])
            if row.get("latest_capital_gain_pct") is not None
            else None
        ),
        latest_ltv_pct=(
            float(row["latest_ltv_pct"]) if row.get("latest_ltv_pct") is not None else None
        ),
        latest_seller_type=str(row.get("latest_seller_type") or "") or None,
        latest_seller_transaction_count=(
            int(row["latest_seller_transaction_count"])
            if row.get("latest_seller_transaction_count") is not None
            else None
        ),
        latest_market_status=str(row.get("latest_market_status") or "") or None,
        lease_start=row["lease_start"],
        lease_end=row["lease_end"],
        days_to_expiry=days,
        status=status,
        priority=str(row["priority"]),
        score=min(int(row["raw_score"]), 100),
        contract_state=str(row.get("contract_state") or "Unknown"),
        match_confidence=str(row["match_confidence"]),
        property_identity_key=str(row.get("property_identity_key") or row["unit_candidate_key"]),
        ownership_timing=ownership_timing,
        lease_evidence_state=lease_evidence_state,
        data_complete_through=row.get("data_complete_through"),
        lead_reason=reason,
        recommended_action=action,
        sale_conversation=sale_candidate,
    )


def _dld_rooms(dxbi_bedrooms: str) -> str:
    if dxbi_bedrooms == "Studio":
        return "Studio"
    if dxbi_bedrooms.endswith(" Bed"):
        return f"{dxbi_bedrooms.removesuffix(' Bed')} B/R"
    return dxbi_bedrooms


def _location_key(value: str) -> str:
    normalized = value.lower()
    for source, target in {
        "jumeriah": "jumeirah",
        "residences": "residence",
        "apartments": "apartment",
    }.items():
        normalized = normalized.replace(source, target)
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _unit_series(value: str | None) -> str | None:
    """Return an explicit unit designator such as the S in 604-S or S-602."""
    normalized = str(value or "").strip().upper()
    if not normalized:
        return None
    parts = [part for part in re.split(r"[^A-Z0-9]+", normalized) if part]
    for part in reversed(parts):
        if part.isalpha() and len(part) <= 3:
            return part
    compact_match = re.match(r"^([A-Z]{1,3})\d", normalized)
    return compact_match.group(1) if compact_match else None


def _same_building(target: str, candidate: str) -> bool:
    """Tolerate DXB building labels with a person/developer prefix or minor spelling drift."""
    target_key = _location_key(target)
    candidate_key = _location_key(candidate)
    if not target_key or not candidate_key:
        return False
    return target_key == candidate_key or (
        min(len(target_key), len(candidate_key)) >= 12
        and (target_key in candidate_key or candidate_key in target_key)
    )


def _within_size(row: dict[str, Any], target_size: float, tolerance: float) -> bool:
    candidate_size = float(row.get("size_sqft") or 0)
    return bool(
        target_size
        and candidate_size
        and abs(candidate_size - target_size) <= target_size * tolerance
    )


def _select_sales_comparables(
    rows: list[dict[str, Any]],
    *,
    building_name: str,
    bedrooms: str,
    unit_number: str | None,
    size: float,
) -> tuple[list[tuple[dict[str, Any], str]], str]:
    target_series = _unit_series(unit_number)
    layout_rows = [
        row
        for row in rows
        if bedrooms in ("", "Not stated") or str(row.get("bedrooms") or "") == bedrooms
    ]
    same_building_rows = [
        row
        for row in layout_rows
        if _same_building(building_name, str(row.get("building_name") or ""))
    ]
    same_building_series = [
        row
        for row in same_building_rows
        if target_series and _unit_series(str(row.get("unit_number") or "")) == target_series
    ]
    same_series_tight = [
        row
        for row in layout_rows
        if target_series
        and _unit_series(str(row.get("unit_number") or "")) == target_series
        and _within_size(row, size, 0.10)
    ]
    same_building_tight = [row for row in same_building_rows if _within_size(row, size, 0.10)]
    layout_tight = [row for row in layout_rows if _within_size(row, size, 0.10)]

    if target_series and same_building_series and len(same_series_tight) >= 2:
        pool = same_series_tight
        basis = (
            f"{target_series}-designated units with the same bedroom layout and within "
            "10% of size; same-building evidence ranked first."
        )
        reason = lambda row: (  # noqa: E731
            f"Same building · {target_series}-series"
            if _same_building(building_name, str(row.get("building_name") or ""))
            else f"{target_series}-series peer"
        )
    elif len(same_building_tight) >= 2:
        pool = same_building_tight
        basis = "Same building and bedroom layout, within 10% of unit size."
        reason = lambda row: "Same building · close size"  # noqa: E731
    elif len(same_building_rows) >= 2:
        pool = same_building_rows
        basis = "Same building and bedroom layout, within 20% of unit size."
        reason = lambda row: "Same building"  # noqa: E731
    elif len(layout_tight) >= 3:
        pool = layout_tight
        basis = "Same area and bedroom layout, within 10% of unit size."
        reason = lambda row: "Same area · close size"  # noqa: E731
    else:
        pool = layout_rows or rows
        basis = "Same area and property type, within 20% of unit size."
        reason = lambda row: "Area fallback"  # noqa: E731

    ranked = sorted(
        pool,
        key=lambda row: (
            not _same_building(building_name, str(row.get("building_name") or "")),
            target_series is None
            or _unit_series(str(row.get("unit_number") or "")) != target_series,
            abs(float(row.get("size_sqft") or 0) - size),
            -row["transaction_date"].toordinal(),
        ),
    )[:10]
    return [(row, reason(row)) for row in ranked], basis


def _select_rental_comparables(
    rows: list[dict[str, Any]],
    *,
    building_name: str,
    bedrooms: str,
    unit_number: str | None,
    size: float,
) -> tuple[list[tuple[dict[str, Any], str]], str]:
    target_series = _unit_series(unit_number)
    layout_rows = [
        row
        for row in rows
        if bedrooms in ("", "Not stated") or str(row.get("bedrooms") or "") == bedrooms
    ]
    same_building_rows = [
        row
        for row in layout_rows
        if _same_building(building_name, str(row.get("building_name") or ""))
    ]
    same_building_tight = [row for row in same_building_rows if _within_size(row, size, 0.10)]
    same_building_series = [
        row
        for row in same_building_rows
        if target_series
        and _unit_series(str(row.get("unit_number") or "")) == target_series
        and _within_size(row, size, 0.20)
    ]
    layout_tight = [row for row in layout_rows if _within_size(row, size, 0.10)]

    if len(same_building_tight) >= 2:
        pool = same_building_tight
        basis = "Same building and bedroom layout, within 10% of unit size."
        reason = lambda row: (  # noqa: E731
            f"Same building · {target_series}-series"
            if target_series and _unit_series(str(row.get("unit_number") or "")) == target_series
            else "Same building · close size"
        )
    elif len(same_building_series) >= 2:
        pool = same_building_series
        basis = f"Same-building {target_series}-designated leases with the same bedroom layout."
        reason = lambda row: f"Same building · {target_series}-series"  # noqa: E731
    elif len(same_building_rows) >= 2:
        pool = same_building_rows
        basis = "Same building and bedroom layout, within 20% of unit size."
        reason = lambda row: "Same building"  # noqa: E731
    elif len(layout_tight) >= 3:
        pool = layout_tight
        basis = "Same area and bedroom layout, within 10% of unit size."
        reason = lambda row: "Same area · close size"  # noqa: E731
    else:
        pool = layout_rows or rows
        basis = "Same area and property type, within 20% of unit size."
        reason = lambda row: "Area fallback"  # noqa: E731

    ranked = sorted(
        pool,
        key=lambda row: (
            not _same_building(building_name, str(row.get("building_name") or "")),
            target_series is None
            or _unit_series(str(row.get("unit_number") or "")) != target_series,
            abs(float(row.get("size_sqft") or 0) - size),
            -row["lease_start"].toordinal(),
        ),
    )[:10]
    return [(row, reason(row)) for row in ranked], basis


async def _tables_exist() -> bool:
    rows = await query(
        """
        SELECT count() AS count
        FROM system.tables
        WHERE
            database = currentDatabase()
            AND name IN (
                {events_table:String},
                {candidate_table:String},
                {sales_table:String},
                {match_table:String}
            )
        """,
        {
            "events_table": DXBI_TABLE,
            "candidate_table": DXBI_CANDIDATE_TABLE,
            "sales_table": "dxbi_sales_unit_events",
            "match_table": "dxbi_rental_sale_matches",
        },
    )
    return bool(rows and rows[0]["count"] == 4)


async def get_dashboard(
    *,
    status: str | None,
    priority: str | None,
    asset_class: str | None,
    property_type: str | None,
    area: str | None,
    project: str | None,
    building: str | None,
    search: str | None,
    breakdown: str,
    limit: int,
    offset: int,
    expired_days: int = 365,
    as_of: date | None = None,
) -> CrmDashboardResponse:
    anchor = as_of or date.today()
    if not await _tables_exist():
        return _empty_dashboard(anchor, limit, offset, breakdown)

    where, filter_params = _where_clause(
        status=status,
        priority=priority,
        area=area,
        project=project,
        building=building,
        search=search,
        asset_class=asset_class,
        property_type=property_type,
    )
    asset_where, asset_filter_params = _where_clause(
        status=status,
        priority=priority,
        area=area,
        project=project,
        building=building,
        search=search,
    )
    facet_where, facet_filter_params = _where_clause(
        status=status,
        priority=priority,
        area=None,
        project=None,
        building=None,
        search=search,
        asset_class=asset_class,
        property_type=property_type,
    )
    params = {
        **filter_params,
        "as_of": anchor.isoformat(),
        "expired_days": expired_days,
        "limit": limit,
        "offset": offset,
    }
    dimension = VALID_BREAKDOWNS[breakdown]

    lead_sql = (
        _LEAD_CTE
        + f"""
        SELECT *
        FROM leads
        WHERE {where}
        ORDER BY raw_score DESC, lease_end ASC, annual_rent_aed DESC
        LIMIT {{limit:Int32}} OFFSET {{offset:Int32}}
        """
    )
    summary_sql = (
        _LEAD_CTE
        + f"""
        SELECT
            count() AS total,
            countIf(priority = 'urgent') AS urgent,
            countIf(
                lead_status = 'expired'
                AND lease_evidence_state = 'unlet_signal'
                AND ownership_timing = 'stable_rental_history'
                AND unit_match_status = 'unique'
            ) AS expired,
            countIf(lead_status = 'expiring_30') AS expiring_30,
            countIf(lead_status = 'expiring_60') AS expiring_60,
            countIf(lead_status = 'expiring_90') AS expiring_90,
            countIf(
                lead_status = 'expired'
                AND lease_evidence_state = 'unlet_signal'
                AND ownership_timing = 'stable_rental_history'
                AND unit_match_status = 'unique'
            ) AS sale_candidates,
            sumIf(
                annual_rent_aed,
                ownership_timing = 'stable_rental_history'
            ) AS annual_rent_at_risk
        FROM leads
        WHERE {where}
        """
    )
    breakdown_sql = (
        _LEAD_CTE
        + f"""
        SELECT
            if({dimension} = '', 'Unresolved hierarchy', {dimension}) AS label,
            count() AS total,
            countIf(priority = 'urgent') AS urgent,
            countIf(lead_status = 'expired') AS expired,
            countIf(lead_status = 'expiring_30') AS expiring_30,
            countIf(lead_status = 'expiring_60') AS expiring_60,
            countIf(lead_status = 'expiring_90') AS expiring_90,
            sumIf(
                annual_rent_aed,
                ownership_timing = 'stable_rental_history'
            ) AS potential_value
        FROM leads
        WHERE {where}
        GROUP BY label
        ORDER BY urgent DESC, total DESC
        LIMIT 12
        """
    )
    asset_breakdown_sql = (
        _LEAD_CTE
        + f"""
        SELECT
            asset_class,
            count() AS total,
            countIf(priority = 'urgent') AS urgent,
            countIf(unit_match_status = 'unique') AS exact_unit_matches,
            sumIf(
                annual_rent_aed,
                ownership_timing = 'stable_rental_history'
            ) AS annual_rent_at_risk,
            arraySort(groupUniqArray(property_subtype)) AS property_types
        FROM leads
        WHERE {asset_where}
        GROUP BY asset_class
        ORDER BY
            multiIf(asset_class = 'residential', 1, asset_class = 'commercial', 2, 3)
        """
    )
    metadata_sql = _filter_metadata_sql(facet_where)
    metadata_params = {
        **facet_filter_params,
        "as_of": anchor.isoformat(),
        "expired_days": expired_days,
        "filter_area": area or "",
        "filter_project": project or "",
    }

    try:
        lead_rows, summary_rows, breakdown_rows, asset_rows, metadata_rows = await asyncio.gather(
            query(lead_sql, params),
            query(summary_sql, params),
            query(breakdown_sql, params),
            query(
                asset_breakdown_sql,
                {
                    **asset_filter_params,
                    "as_of": anchor.isoformat(),
                    "expired_days": expired_days,
                },
            ),
            query(metadata_sql, metadata_params),
        )
    except Exception as exc:
        logger.exception("CRM dashboard query failed")
        raise HTTPException(
            status_code=503, detail="CRM lead data is temporarily unavailable"
        ) from exc

    summary_row = summary_rows[0] if summary_rows else {}
    metadata = metadata_rows[0] if metadata_rows else {}
    leads = [_lead_from_row(row) for row in lead_rows]
    return CrmDashboardResponse(
        leads=leads,
        total=int(summary_row.get("total") or 0),
        limit=limit,
        offset=offset,
        summary=CrmSummary(
            total_leads=int(summary_row.get("total") or 0),
            urgent=int(summary_row.get("urgent") or 0),
            expired_unlet=int(summary_row.get("expired") or 0),
            expiring_30_days=int(summary_row.get("expiring_30") or 0),
            expiring_31_to_60_days=int(summary_row.get("expiring_60") or 0),
            expiring_61_to_90_days=int(summary_row.get("expiring_90") or 0),
            sale_conversation_candidates=int(summary_row.get("sale_candidates") or 0),
            annual_rent_at_risk_aed=int(summary_row.get("annual_rent_at_risk") or 0),
        ),
        asset_breakdown=[
            CrmAssetBreakdownItem(
                asset_class=str(row["asset_class"]),
                total=int(row["total"]),
                urgent=int(row["urgent"]),
                exact_unit_matches=int(row["exact_unit_matches"]),
                annual_rent_at_risk_aed=int(row["annual_rent_at_risk"] or 0),
                property_types=list(row.get("property_types") or []),
            )
            for row in asset_rows
        ],
        breakdown=[
            CrmBreakdownItem(
                label=str(row["label"]),
                total=int(row["total"]),
                urgent=int(row["urgent"]),
                expired=int(row["expired"]),
                expiring_30=int(row["expiring_30"]),
                expiring_60=int(row["expiring_60"]),
                expiring_90=int(row["expiring_90"]),
                potential_value_aed=int(row["potential_value"] or 0),
            )
            for row in breakdown_rows
        ],
        breakdown_level=breakdown,
        filters=CrmFilters(
            areas=list(metadata.get("areas") or []),
            projects=list(metadata.get("projects") or []),
            buildings=list(metadata.get("buildings") or []),
            property_types=sorted(
                {
                    str(property_type)
                    for row in asset_rows
                    if not asset_class or row["asset_class"] == asset_class
                    for property_type in row.get("property_types") or []
                }
            ),
        ),
        coverage=CrmCoverage(
            rental_source="Lease transaction registry",
            rental_start_date=metadata.get("min_date"),
            rental_end_date=metadata.get("max_date"),
            rental_rows=int(metadata.get("rows") or 0),
            exact_unit_ids_available=bool(metadata.get("exact_unit_matches")),
            exact_unit_matches=int(metadata.get("exact_unit_matches") or 0),
            data_complete_through=metadata.get("data_complete_through"),
            matching_method=(
                "Unique sale match on building, area, bedroom layout, exact size, "
                "purchase evidence, and a stable exact-unit lease timeline"
            ),
            caveat=(
                "An exact-unit lease is flagged as unlet immediately after expiry when no later "
                "registered lease is observed. Sales on or after lease expiry are excluded; "
                "sales during an active tenancy remain ownership-transition reviews."
            ),
        ),
        as_of=anchor,
    )


async def get_lead_detail(lead_id: str, as_of: date | None = None) -> CrmLeadDetailResponse:
    anchor = as_of or date.today()
    if not await _tables_exist():
        raise HTTPException(status_code=404, detail="CRM lead data has not been loaded")

    current_rows = await _query_with_legacy_rentals(
        _LEAD_CTE + " SELECT * FROM leads WHERE event_key = {lead_id:String} LIMIT 1",
        {
            "as_of": anchor.isoformat(),
            "expired_days": 3650,
            "lead_id": lead_id,
        },
    )
    if not current_rows:
        raise HTTPException(status_code=404, detail="CRM lead not found")
    lead = _lead_from_row(current_rows[0])
    row = current_rows[0]

    rental_query = _query_with_legacy_rentals(
        """
        SELECT
            event_key,
            lease_start,
            lease_end,
            annual_rent_aed,
            contract_state
        FROM dxbi_rental_events FINAL
        WHERE unit_candidate_key = {candidate_key:String}
        ORDER BY lease_start DESC
        LIMIT 50
        """,
        {"candidate_key": lead.unit_candidate_key},
    )

    exact_sales_rows: list[dict[str, Any]] = []
    dld_sales_rows: list[dict[str, Any]] = []
    building_name = str(row.get("building_name") or "")
    if lead.unit_number and building_name:
        rental_rows, exact_sales_rows = await asyncio.gather(
            rental_query,
            query(
                """
                SELECT
                    sale_key,
                    transaction_date AS sale_date,
                    sale_amount_aed,
                    price_per_sqft_aed,
                    capital_gain_pct,
                    ltv_pct,
                    seller_type,
                    seller_transaction_count,
                    market_status,
                    detail_url
                FROM dxbi_sales_unit_events FINAL
                WHERE
                    unit_number = {unit_number:String}
                    AND building_key = {building_key:String}
                ORDER BY transaction_date DESC
                LIMIT 25
                """,
                {
                    "unit_number": lead.unit_number,
                    "building_key": _location_key(building_name),
                },
            ),
        )
    elif building_name:
        rental_rows, dld_sales_rows = await asyncio.gather(
            rental_query,
            query(
                """
                SELECT
                    transaction_id,
                    toDate(instance_date) AS sale_date,
                    trans_value,
                    procedure_name_en
                FROM ch_transactions
                WHERE
                    trans_group_en = 'Sales'
                    AND positionCaseInsensitiveUTF8(building_name_en, {building:String}) > 0
                    AND ({bedrooms:String} = '' OR rooms_en = {bedrooms:String})
                    AND (
                        {size_sqft:Float64} = 0
                        OR abs(procedure_area * 10.7639 - {size_sqft:Float64})
                            <= greatest(25, {size_sqft:Float64} * 0.03)
                    )
                ORDER BY instance_date DESC
                LIMIT 25
                """,
                {
                    "building": building_name,
                    "bedrooms": _dld_rooms(str(row.get("bedrooms") or "")),
                    "size_sqft": float(row.get("size_sqft") or 0),
                },
            ),
        )
    else:
        rental_rows = await rental_query

    timeline = [
        CrmTimelineEvent(
            event_id=str(item["event_key"]),
            event_type="lease",
            event_date=item["lease_start"],
            end_date=item["lease_end"],
            title=f"{item.get('contract_state') or 'Lease'} contract",
            description=f"Annual rent AED {int(item.get('annual_rent_aed') or 0):,}",
            amount_aed=int(item.get("annual_rent_aed") or 0),
            source="Lease transaction registry",
            confidence=lead.match_confidence,
        )
        for item in rental_rows
    ]
    for item in exact_sales_rows:
        timeline.append(
            CrmTimelineEvent(
                event_id=str(item["sale_key"]),
                event_type="sale",
                event_date=item["sale_date"],
                title=f"Unit {lead.unit_number} purchased",
                description="Exact sale record matched to this unit number.",
                amount_aed=int(item.get("sale_amount_aed") or 0),
                source="Sales transaction registry",
                confidence="high",
                ltv_pct=(float(item["ltv_pct"]) if item.get("ltv_pct") is not None else None),
                capital_gain_pct=(
                    float(item["capital_gain_pct"])
                    if item.get("capital_gain_pct") is not None
                    else None
                ),
            )
        )
    for item in dld_sales_rows:
        timeline.append(
            CrmTimelineEvent(
                event_id=str(item["transaction_id"]),
                event_type="sale",
                event_date=item["sale_date"],
                title=str(item.get("procedure_name_en") or "Candidate sale"),
                description="DLD sale matched on building, layout, and size.",
                amount_aed=int(item.get("trans_value") or 0),
                source="DLD full sales registry",
                confidence="medium",
            )
        )
    timeline.sort(key=lambda event: event.event_date, reverse=True)
    agent_signals = _agent_signals(lead)
    if lead.asset_class == "commercial":
        next_best_actions = [
            (
                f"Use unit {lead.unit_number} to resolve the current title-deed owner and contact."
                if lead.unit_number
                else "Resolve the exact unit and current title-deed owner before contact."
            ),
            "Lead with an occupancy, rent, and renewal review or a commercial leasing mandate.",
            "If the owner is open to an exit, prepare an investment-sale valuation using current commercial comparables.",
        ]
    else:
        next_best_actions = [
            (
                f"Use unit {lead.unit_number} to resolve the current title-deed owner and contact."
                if lead.unit_number
                else "Resolve the exact unit and current title-deed owner before contact."
            ),
            "Lead with a rent review and renewal or re-letting plan.",
            "If the owner is open to an exit, prepare a sale valuation using current comparables.",
        ]
    subtype_evidence = (
        f" The matched sale identifies the unit as {lead.property_subtype.lower()}."
        if lead.asset_class == "commercial"
        and lead.property_subtype != "Commercial"
        and lead.unit_number
        else ""
    )
    return CrmLeadDetailResponse(
        lead=lead,
        timeline=timeline,
        next_best_actions=next_best_actions,
        agent_signals=agent_signals,
        match_explanation=(
            (
                f"Unit {lead.unit_number} is a unique sales match on building, area, "
                "bedroom layout, exact size, and reported purchase price. Owner identity "
                f"still requires title-deed/contact enrichment.{subtype_evidence}"
            )
            if lead.unit_number
            else (
                "No unique unit number could be resolved. Lease events are grouped by "
                "building/location, bedroom layout, exact area, and latest purchase price; "
                "candidate DLD sales are not confirmed title-deed links."
            )
        ),
        generated_at=datetime.now(timezone.utc),
    )


def _agent_signals(lead: CrmLead) -> list[str]:
    signals: list[str] = []
    if lead.latest_ltv_pct is not None:
        if 0 < lead.latest_ltv_pct <= 100:
            signals.append(
                f"The source reported {lead.latest_ltv_pct:g}% LTV on the latest purchase. "
                "Treat this as financing-at-purchase evidence, not a current mortgage balance."
            )
        else:
            signals.append(
                f"The source displays {lead.latest_ltv_pct:g}% LTV on the latest purchase, "
                "which is outside a normal range; do not use it for mortgage outreach."
            )
    if lead.latest_capital_gain_pct is not None:
        direction = "gain" if lead.latest_capital_gain_pct >= 0 else "loss"
        signals.append(
            f"The source reports a {abs(lead.latest_capital_gain_pct):g}% {direction} versus "
            "the preceding recorded sale."
        )
    if lead.latest_seller_type:
        seller = lead.latest_seller_type
        if lead.latest_seller_transaction_count:
            seller += f" ({lead.latest_seller_transaction_count} source-reported transactions)"
        signals.append(f"Latest sale was recorded as sold by {seller}.")
    if lead.gross_yield_pct is not None:
        signals.append(
            f"Current contract rent implies a {lead.gross_yield_pct:.2f}% gross yield "
            "on the latest recorded purchase price."
        )
    return signals


def _saved_lead_response(
    saved: CrmSavedLead,
    *,
    live_lead: CrmLead | None = None,
) -> CrmSavedLeadResponse:
    if saved.id is None:
        raise HTTPException(status_code=500, detail="Saved CRM lead is missing an id")
    snapshot = dict(saved.snapshot)
    property_type = str(snapshot.get("property_type") or "Property")
    if "asset_class" not in snapshot:
        snapshot["asset_class"] = (
            "residential"
            if property_type in {"Apartment", "Villa"}
            else "commercial"
            if property_type == "Commercial"
            else "other"
        )
    snapshot.setdefault("property_subtype", property_type)
    return CrmSavedLeadResponse(
        id=saved.id,
        lead=live_lead or CrmLead.model_validate(snapshot),
        created_at=saved.created_at,
        updated_at=saved.updated_at,
    )


async def list_saved_leads(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str,
) -> list[CrmSavedLeadResponse]:
    result = await db.exec(
        select(CrmSavedLead)
        .where(
            CrmSavedLead.user_id == user_id,
            CrmSavedLead.organization_id == organization_id,
        )
        .order_by(CrmSavedLead.updated_at.desc())
    )
    saved_rows = list(result.all())
    if not saved_rows:
        return []

    candidate_keys = [saved.unit_candidate_key for saved in saved_rows]
    live_rows = await _query_with_legacy_rentals(
        _LEAD_CTE
        + """
        SELECT
            i.unit_candidate_key AS saved_candidate_key,
            l.*
        FROM identified_unit AS i
        ANY INNER JOIN leads AS l USING (property_identity_key)
        WHERE i.unit_candidate_key IN {candidate_keys:Array(String)}
        """,
        {
            "as_of": date.today().isoformat(),
            "expired_days": 3650,
            "candidate_keys": candidate_keys,
        },
        saved_candidates=True,
    )
    live_by_saved_key = {str(row["saved_candidate_key"]): _lead_from_row(row) for row in live_rows}
    return [
        _saved_lead_response(
            saved,
            live_lead=live_by_saved_key.get(saved.unit_candidate_key),
        )
        for saved in saved_rows
    ]


async def save_lead(
    db: AsyncSession,
    *,
    lead_id: str,
    user_id: str,
    organization_id: str,
) -> CrmSavedLeadResponse:
    detail = await get_lead_detail(lead_id)
    now = datetime.now(timezone.utc)
    result = await db.exec(
        select(CrmSavedLead).where(
            CrmSavedLead.user_id == user_id,
            CrmSavedLead.organization_id == organization_id,
            CrmSavedLead.unit_candidate_key == detail.lead.unit_candidate_key,
        )
    )
    saved = result.first()
    snapshot = detail.lead.model_dump(mode="json")
    if saved is None:
        saved = CrmSavedLead(
            user_id=user_id,
            organization_id=organization_id,
            lead_id=lead_id,
            unit_candidate_key=detail.lead.unit_candidate_key,
            snapshot=snapshot,
            created_at=now,
            updated_at=now,
        )
    else:
        saved.lead_id = lead_id
        saved.snapshot = snapshot
        saved.updated_at = now
    db.add(saved)
    await db.commit()
    await db.refresh(saved)
    return _saved_lead_response(saved)


async def delete_saved_lead(
    db: AsyncSession,
    *,
    saved_id: int,
    user_id: str,
    organization_id: str,
) -> None:
    result = await db.exec(
        select(CrmSavedLead).where(
            CrmSavedLead.id == saved_id,
            CrmSavedLead.user_id == user_id,
            CrmSavedLead.organization_id == organization_id,
        )
    )
    saved = result.first()
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved CRM lead not found")
    await db.delete(saved)
    await db.commit()


def _workspace_summary(
    workspace: CrmLeadWorkspace,
    *,
    note_count: int = 0,
) -> CrmWorkspaceSummary:
    if workspace.id is None:
        raise HTTPException(status_code=500, detail="CRM workspace is missing an id")
    return CrmWorkspaceSummary(
        id=workspace.id,
        lead_id=workspace.lead_id,
        unit_candidate_key=workspace.unit_candidate_key,
        pipeline_status=workspace.pipeline_status,
        highlight_color=workspace.highlight_color,
        owner_name=workspace.owner_name,
        owner_email=workspace.owner_email,
        owner_phone=workspace.owner_phone,
        next_follow_up=workspace.next_follow_up,
        tags=list(workspace.tags or []),
        note_count=note_count,
        updated_at=workspace.updated_at,
    )


def _note_response(note: CrmLeadNote) -> CrmLeadNoteResponse:
    if note.id is None:
        raise HTTPException(status_code=500, detail="CRM note is missing an id")
    return CrmLeadNoteResponse(
        id=note.id,
        body=note.body,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def _workspace_for_candidate(
    db: AsyncSession,
    *,
    unit_candidate_key: str,
    user_id: str,
    organization_id: str,
) -> CrmLeadWorkspace | None:
    result = await db.exec(
        select(CrmLeadWorkspace).where(
            CrmLeadWorkspace.user_id == user_id,
            CrmLeadWorkspace.organization_id == organization_id,
            CrmLeadWorkspace.unit_candidate_key == unit_candidate_key,
        )
    )
    return result.first()


async def _candidate_key_for_lead(lead_id: str) -> str:
    rows = await _query_with_legacy_rentals(
        """
        SELECT unit_candidate_key
        FROM dxbi_rental_unit_candidates FINAL
        WHERE event_key = {lead_id:String}
        LIMIT 1
        """,
        {"lead_id": lead_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="CRM lead not found")
    return str(rows[0]["unit_candidate_key"])


async def _workspace_notes(
    db: AsyncSession,
    *,
    workspace_id: int,
    user_id: str,
    organization_id: str,
) -> list[CrmLeadNote]:
    result = await db.exec(
        select(CrmLeadNote)
        .where(
            CrmLeadNote.workspace_id == workspace_id,
            CrmLeadNote.user_id == user_id,
            CrmLeadNote.organization_id == organization_id,
        )
        .order_by(CrmLeadNote.created_at.desc())
    )
    return list(result.all())


async def list_lead_workspaces(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str,
) -> list[CrmWorkspaceSummary]:
    result = await db.exec(
        select(CrmLeadWorkspace)
        .where(
            CrmLeadWorkspace.user_id == user_id,
            CrmLeadWorkspace.organization_id == organization_id,
        )
        .order_by(CrmLeadWorkspace.updated_at.desc())
    )
    workspaces = list(result.all())
    if not workspaces:
        return []
    workspace_ids = [workspace.id for workspace in workspaces if workspace.id is not None]
    notes_result = await db.exec(
        select(CrmLeadNote).where(
            CrmLeadNote.workspace_id.in_(workspace_ids),  # type: ignore[union-attr]
            CrmLeadNote.user_id == user_id,
            CrmLeadNote.organization_id == organization_id,
        )
    )
    note_counts: dict[int, int] = {}
    for note in notes_result.all():
        note_counts[note.workspace_id] = note_counts.get(note.workspace_id, 0) + 1
    return [
        _workspace_summary(
            workspace,
            note_count=note_counts.get(workspace.id or 0, 0),
        )
        for workspace in workspaces
    ]


async def get_lead_workspace(
    db: AsyncSession,
    *,
    lead_id: str,
    user_id: str,
    organization_id: str,
) -> CrmWorkspaceResponse:
    unit_candidate_key = await _candidate_key_for_lead(lead_id)
    workspace = await _workspace_for_candidate(
        db,
        unit_candidate_key=unit_candidate_key,
        user_id=user_id,
        organization_id=organization_id,
    )
    if workspace is None:
        return CrmWorkspaceResponse(
            id=None,
            lead_id=lead_id,
            unit_candidate_key=unit_candidate_key,
            pipeline_status="new",
            highlight_color="none",
            updated_at=datetime.now(timezone.utc),
            notes=[],
        )
    notes = await _workspace_notes(
        db,
        workspace_id=workspace.id or 0,
        user_id=user_id,
        organization_id=organization_id,
    )
    summary = _workspace_summary(workspace, note_count=len(notes))
    return CrmWorkspaceResponse(
        **summary.model_dump(),
        notes=[_note_response(note) for note in notes],
    )


def _clean_workspace_value(value: str | None) -> str | None:
    return str(value or "").strip() or None


async def update_lead_workspace(
    db: AsyncSession,
    *,
    lead_id: str,
    payload: CrmWorkspaceUpdate,
    user_id: str,
    organization_id: str,
) -> CrmWorkspaceResponse:
    unit_candidate_key = await _candidate_key_for_lead(lead_id)
    workspace = await _workspace_for_candidate(
        db,
        unit_candidate_key=unit_candidate_key,
        user_id=user_id,
        organization_id=organization_id,
    )
    now = datetime.now(timezone.utc)
    if workspace is None:
        workspace = CrmLeadWorkspace(
            user_id=user_id,
            organization_id=organization_id,
            lead_id=lead_id,
            unit_candidate_key=unit_candidate_key,
            created_at=now,
            updated_at=now,
        )
    changes = payload.model_dump(exclude_unset=True)
    for field in ("pipeline_status", "highlight_color", "next_follow_up"):
        if field in changes:
            setattr(workspace, field, changes[field])
    for field in ("owner_name", "owner_email", "owner_phone"):
        if field in changes:
            setattr(workspace, field, _clean_workspace_value(changes[field]))
    if "tags" in changes:
        normalized_tags: list[str] = []
        for tag in changes["tags"] or []:
            clean_tag = str(tag).strip()
            if clean_tag and clean_tag.casefold() not in {
                existing.casefold() for existing in normalized_tags
            }:
                normalized_tags.append(clean_tag[:40])
        workspace.tags = normalized_tags[:12]
    workspace.lead_id = lead_id
    workspace.updated_at = now
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    notes = await _workspace_notes(
        db,
        workspace_id=workspace.id or 0,
        user_id=user_id,
        organization_id=organization_id,
    )
    summary = _workspace_summary(workspace, note_count=len(notes))
    return CrmWorkspaceResponse(
        **summary.model_dump(),
        notes=[_note_response(note) for note in notes],
    )


async def add_lead_note(
    db: AsyncSession,
    *,
    lead_id: str,
    payload: CrmNoteCreate,
    user_id: str,
    organization_id: str,
) -> CrmWorkspaceResponse:
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Note cannot be empty")
    workspace_response = await update_lead_workspace(
        db,
        lead_id=lead_id,
        payload=CrmWorkspaceUpdate(),
        user_id=user_id,
        organization_id=organization_id,
    )
    if workspace_response.id is None:
        raise HTTPException(status_code=500, detail="CRM workspace was not created")
    now = datetime.now(timezone.utc)
    note = CrmLeadNote(
        workspace_id=workspace_response.id,
        user_id=user_id,
        organization_id=organization_id,
        body=body,
        created_at=now,
        updated_at=now,
    )
    db.add(note)
    await db.commit()
    return await get_lead_workspace(
        db,
        lead_id=lead_id,
        user_id=user_id,
        organization_id=organization_id,
    )


async def delete_lead_note(
    db: AsyncSession,
    *,
    note_id: int,
    user_id: str,
    organization_id: str,
) -> None:
    result = await db.exec(
        select(CrmLeadNote).where(
            CrmLeadNote.id == note_id,
            CrmLeadNote.user_id == user_id,
            CrmLeadNote.organization_id == organization_id,
        )
    )
    note = result.first()
    if note is None:
        raise HTTPException(status_code=404, detail="CRM note not found")
    await db.delete(note)
    await db.commit()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _quarter_start(value: date) -> date:
    return date(value.year, ((value.month - 1) // 3) * 3 + 1, 1)


def _shift_quarters(value: date, quarters: int) -> date:
    quarter_number = value.year * 4 + (value.month - 1) // 3 + quarters
    year, quarter = divmod(quarter_number, 4)
    return date(year, quarter * 3 + 1, 1)


def _quarter_label(value: date) -> str:
    return f"Q{((value.month - 1) // 3) + 1} {value.year}"


def _fixed_mix_series(
    rows: list[dict[str, Any]],
) -> tuple[dict[date, float], dict[date, int]]:
    """Create a stable 75% apartment / 25% villa quarterly AED/sqft series."""
    grouped: dict[date, dict[str, tuple[float, int]]] = {}
    for row in rows:
        quarter = row["quarter"]
        segment = str(row.get("segment") or "")
        median_psf = float(row.get("median_psf") or 0)
        transactions = int(row.get("transactions") or 0)
        if median_psf <= 0 or segment not in {"Apartment", "Villa"}:
            continue
        grouped.setdefault(quarter, {})[segment] = (median_psf, transactions)

    values: dict[date, float] = {}
    counts: dict[date, int] = {}
    for quarter, segments in grouped.items():
        if "Apartment" not in segments or "Villa" not in segments:
            continue
        apartment, apartment_count = segments["Apartment"]
        villa, villa_count = segments["Villa"]
        values[quarter] = apartment * 0.75 + villa * 0.25
        counts[quarter] = apartment_count + villa_count
    return values, counts


def _commercial_mix_series(
    rows: list[dict[str, Any]],
) -> tuple[dict[date, float], dict[date, int]]:
    """Create a stable 80% office / 20% shop quarterly AED/sqft series."""
    grouped: dict[date, dict[str, tuple[float, int]]] = {}
    for row in rows:
        quarter = row["quarter"]
        segment = str(row.get("segment") or "")
        median_psf = float(row.get("median_psf") or 0)
        transactions = int(row.get("transactions") or 0)
        if median_psf <= 0 or segment not in {"Office", "Shop"}:
            continue
        grouped.setdefault(quarter, {})[segment] = (median_psf, transactions)

    values: dict[date, float] = {}
    counts: dict[date, int] = {}
    for quarter, segments in grouped.items():
        if "Office" not in segments or "Shop" not in segments:
            continue
        office, office_count = segments["Office"]
        shop, shop_count = segments["Shop"]
        values[quarter] = office * 0.8 + shop * 0.2
        counts[quarter] = office_count + shop_count
    return values, counts


def _single_series(
    rows: list[dict[str, Any]],
) -> tuple[dict[date, float], dict[date, int]]:
    values: dict[date, float] = {}
    counts: dict[date, int] = {}
    for row in rows:
        median_psf = float(row.get("median_psf") or 0)
        if median_psf <= 0:
            continue
        quarter = row["quarter"]
        values[quarter] = median_psf
        counts[quarter] = int(row.get("transactions") or 0)
    return values, counts


def _rebase_series(values: dict[date, float]) -> dict[date, float]:
    if not values:
        return {}
    base_value = values[min(values)]
    if base_value <= 0:
        return {}
    return {quarter: round(value / base_value * 100, 2) for quarter, value in values.items()}


def _change_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current / previous - 1) * 100, 2)


async def _build_price_index(
    lead: CrmLead,
    *,
    anchor: date,
) -> CrmPriceIndex:
    current_quarter = _quarter_start(anchor)
    index_start = _shift_quarters(current_quarter, -20)
    is_commercial = lead.asset_class == "commercial"
    dld_sql = """
        SELECT
            toStartOfQuarter(instance_date) AS quarter,
            if(
                {is_commercial:UInt8} = 1,
                property_sub_type_en,
                if(property_type_en = 'Villa', 'Villa', 'Apartment')
            ) AS segment,
            uniqExact(transaction_id) AS transactions,
            median(trans_value / (procedure_area * 10.7639)) AS median_psf
        FROM ch_transactions
        WHERE
            trans_group_en = 'Sales'
            AND procedure_name_en IN (
                'Sell',
                'Sale',
                'Delayed Sell',
                'Sell - Pre registration',
                'Sale On Payment Plan'
            )
            AND (
                (
                    {is_commercial:UInt8} = 1
                    AND property_usage_en = 'Commercial'
                    AND property_type_en = 'Unit'
                    AND property_sub_type_en IN ('Office', 'Shop')
                )
                OR (
                    {is_commercial:UInt8} = 0
                    AND property_usage_en = 'Residential'
                    AND property_type_en IN ('Unit', 'Villa')
                )
            )
            AND instance_date >= {index_start:Date}
            AND instance_date < {current_quarter:Date}
            AND procedure_area > 0
            AND trans_value > 0
            AND trans_value / (procedure_area * 10.7639) BETWEEN 200 AND 12000
        GROUP BY quarter, segment
        ORDER BY quarter, segment
    """
    transaction_sql = """
        SELECT
            toStartOfQuarter(transaction_date) AS quarter,
            property_type AS segment,
            uniqExact(sale_key) AS transactions,
            median(price_per_sqft_aed) AS median_psf
        FROM dxbi_sales_unit_events FINAL
        WHERE
            transaction_date >= {index_start:Date}
            AND transaction_date < {current_quarter:Date}
            AND (
                ({is_commercial:UInt8} = 1 AND property_type IN ('Office', 'Shop'))
                OR (
                    {is_commercial:UInt8} = 0
                    AND property_type IN ('Apartment', 'Villa')
                )
            )
            AND price_per_sqft_aed BETWEEN 200 AND 12000
        GROUP BY quarter, segment
        ORDER BY quarter, segment
    """
    segment_type = (
        lead.property_subtype
        if lead.property_subtype in {"Apartment", "Villa", "Office", "Shop"}
        else ""
    )
    segment_sql = """
        SELECT
            toStartOfQuarter(transaction_date) AS quarter,
            uniqExact(sale_key) AS transactions,
            median(price_per_sqft_aed) AS median_psf
        FROM dxbi_sales_unit_events FINAL
        WHERE
            transaction_date >= {index_start:Date}
            AND transaction_date < {current_quarter:Date}
            AND area_key = {area_key:String}
            AND ({segment_type:String} = '' OR property_type = {segment_type:String})
            AND price_per_sqft_aed BETWEEN 200 AND 12000
        GROUP BY quarter
        ORDER BY quarter
    """
    params = {
        "index_start": index_start.isoformat(),
        "current_quarter": current_quarter.isoformat(),
        "area_key": _location_key(lead.area_name),
        "segment_type": segment_type,
        "is_commercial": int(is_commercial),
    }
    dld_rows, transaction_rows, segment_rows = await asyncio.gather(
        query(dld_sql, params),
        query(transaction_sql, params),
        query(segment_sql, params),
    )

    mix_series = _commercial_mix_series if is_commercial else _fixed_mix_series
    dld_psf, dld_counts = mix_series(dld_rows)
    transaction_psf, transaction_counts = mix_series(transaction_rows)
    segment_psf, segment_counts = _single_series(segment_rows)
    dld_index = _rebase_series(dld_psf)
    transaction_index = _rebase_series(transaction_psf)
    segment_index = _rebase_series(segment_psf)

    points: list[CrmPriceIndexPoint] = []
    quarter = index_start
    while quarter < current_quarter:
        source_indexes = [
            value
            for value in (dld_index.get(quarter), transaction_index.get(quarter))
            if value is not None
        ]
        source_psf = [
            value
            for value in (dld_psf.get(quarter), transaction_psf.get(quarter))
            if value is not None
        ]
        if source_indexes:
            points.append(
                CrmPriceIndexPoint(
                    quarter=quarter,
                    label=_quarter_label(quarter),
                    dubai_index=round(sum(source_indexes) / len(source_indexes), 2),
                    dld_index=dld_index.get(quarter),
                    transaction_index=transaction_index.get(quarter),
                    segment_index=segment_index.get(quarter),
                    dubai_median_psf_aed=(
                        int(round(sum(source_psf) / len(source_psf))) if source_psf else None
                    ),
                    segment_median_psf_aed=(
                        int(round(segment_psf[quarter])) if quarter in segment_psf else None
                    ),
                    dld_transactions=dld_counts.get(quarter, 0),
                    transaction_count=transaction_counts.get(quarter, 0),
                    segment_transactions=segment_counts.get(quarter, 0),
                )
            )
        quarter = _shift_quarters(quarter, 1)

    if not points:
        points = [
            CrmPriceIndexPoint(
                quarter=index_start,
                label=_quarter_label(index_start),
                dubai_index=100,
            )
        ]
    latest = points[-1]
    year_ago_quarter = _shift_quarters(latest.quarter, -4)
    year_ago = next(
        (point for point in points if point.quarter == year_ago_quarter),
        None,
    )
    latest_segment_point = next(
        (point for point in reversed(points) if point.segment_index is not None),
        None,
    )
    segment_year_ago = (
        next(
            (
                point
                for point in points
                if point.quarter == _shift_quarters(latest_segment_point.quarter, -4)
            ),
            None,
        )
        if latest_segment_point
        else None
    )
    segment_name = f"{lead.area_name} · {lead.property_subtype}"
    return CrmPriceIndex(
        name=(
            "Vitevue Dubai Commercial Price Index"
            if is_commercial
            else "Vitevue Dubai Residential Price Index"
        ),
        base_period=points[0].quarter,
        latest_period=latest.quarter,
        current_index=latest.dubai_index,
        change_since_base_pct=round(latest.dubai_index - points[0].dubai_index, 2),
        year_over_year_pct=_change_pct(
            latest.dubai_index,
            year_ago.dubai_index if year_ago else None,
        ),
        current_median_psf_aed=latest.dubai_median_psf_aed,
        segment_name=segment_name,
        segment_current_index=(
            latest_segment_point.segment_index if latest_segment_point else None
        ),
        segment_year_over_year_pct=_change_pct(
            latest_segment_point.segment_index if latest_segment_point else None,
            segment_year_ago.segment_index if segment_year_ago else None,
        ),
        segment_current_median_psf_aed=(
            latest_segment_point.segment_median_psf_aed if latest_segment_point else None
        ),
        points=points,
        methodology=(
            (
                "Quarterly commercial AED/sqft, rebased to 100 at the first displayed quarter. "
                "Dubai uses a fixed 80% office / 20% shop mix and averages independently "
            )
            if is_commercial
            else (
                "Quarterly residential AED/sqft, rebased to 100 at the first displayed quarter. "
                "Dubai uses a fixed 75% apartment / 25% villa mix and averages independently "
            )
        )
        + (
            "rebased DLD registry and transaction-platform series when both are complete; "
            "the transaction series fills quarters where a DLD stratum is incomplete. "
            "The local segment uses "
            "sales for the subject area and property type. Current partial quarters are excluded. "
            "This is an internal analytical index, not an official government index or appraisal."
        ),
    )


async def get_property_report(
    lead_id: str,
    *,
    as_of: date | None = None,
) -> CrmPropertyReportResponse:
    anchor = as_of or date.today()
    period_start = anchor - timedelta(days=365)
    detail = await get_lead_detail(lead_id, as_of=anchor)
    lead = detail.lead
    size = float(lead.size_sqft or 0)
    low_size = size * 0.8 if size else 0
    high_size = size * 1.2 if size else 1_000_000

    sales_sql = """
        SELECT
            transaction_date,
            building_name,
            unit_number,
            property_type,
            bedrooms,
            size_sqft,
            sale_amount_aed,
            price_per_sqft_aed,
            detail_url
        FROM dxbi_sales_unit_events FINAL
        WHERE
            transaction_date BETWEEN {period_start:Date} AND {period_end:Date}
            AND area_key = {area_key:String}
            AND (
                {sales_property_type:String} = ''
                OR property_type = {sales_property_type:String}
                OR (
                    {sales_property_type:String} = 'Commercial'
                    AND property_type IN (
                        'Office',
                        'Shop',
                        'Warehouse',
                        'Show Rooms',
                        'Workshop',
                        'Clinic',
                        'Commercial'
                    )
                )
            )
            AND size_sqft BETWEEN {low_size:Float64} AND {high_size:Float64}
        ORDER BY
            abs(size_sqft - {size:Float64}) ASC,
            transaction_date DESC
        LIMIT 250
    """
    rentals_sql = """
        SELECT
            r.lease_start,
            r.building_name,
            m.unit_number,
            m.match_status AS unit_match_status,
            r.property_type,
            r.bedrooms,
            r.size_sqft,
            r.annual_rent_aed
        FROM dxbi_rental_events AS r FINAL
        LEFT JOIN dxbi_rental_sale_matches AS m FINAL USING (unit_candidate_key)
        WHERE
            r.lease_start BETWEEN {period_start:Date} AND {period_end:Date}
            AND r.event_key != {lead_id:String}
            AND r.area_name = {area_name:String}
            AND (
                {rental_property_type:String} = ''
                OR r.property_type = {rental_property_type:String}
            )
            AND ({bedrooms:String} = '' OR r.bedrooms = {bedrooms:String})
            AND r.size_sqft BETWEEN {low_size:Float64} AND {high_size:Float64}
        ORDER BY
            abs(r.size_sqft - {size:Float64}) ASC,
            r.lease_start DESC
        LIMIT 250
    """
    params = {
        "period_start": period_start.isoformat(),
        "period_end": anchor.isoformat(),
        "area_key": _location_key(lead.area_name),
        "area_name": lead.area_name,
        "building_key": _location_key(lead.building_name),
        "building_name": lead.building_name,
        "sales_property_type": (
            lead.property_subtype if lead.property_subtype != "Commercial" else lead.property_type
        ),
        "rental_property_type": lead.property_type,
        "bedrooms": "" if lead.bedrooms == "Not stated" else lead.bedrooms,
        "low_size": low_size,
        "high_size": high_size,
        "size": size,
        "lead_id": lead.lead_id,
    }
    sale_rows, rental_rows, price_index = await asyncio.gather(
        query(sales_sql, params),
        query(rentals_sql, params),
        _build_price_index(lead, anchor=anchor),
    )
    selected_sale_rows, sales_basis = _select_sales_comparables(
        sale_rows,
        building_name=lead.building_name,
        bedrooms=lead.bedrooms,
        unit_number=lead.unit_number,
        size=size,
    )
    selected_rental_rows, rentals_basis = _select_rental_comparables(
        rental_rows,
        building_name=lead.building_name,
        bedrooms=lead.bedrooms,
        unit_number=lead.unit_number,
        size=size,
    )
    sale_comps = [
        CrmSaleComparable(
            transaction_date=row["transaction_date"],
            building_name=str(row.get("building_name") or ""),
            unit_number=str(row.get("unit_number") or ""),
            unit_series=_unit_series(str(row.get("unit_number") or "")),
            property_type=str(row.get("property_type") or ""),
            bedrooms=str(row.get("bedrooms") or ""),
            size_sqft=float(row.get("size_sqft") or 0),
            sale_amount_aed=int(row.get("sale_amount_aed") or 0),
            price_per_sqft_aed=(
                float(row["price_per_sqft_aed"])
                if row.get("price_per_sqft_aed") is not None
                else None
            ),
            selection_reason=selection_reason,
        )
        for row, selection_reason in selected_sale_rows
    ]
    rental_comps = [
        CrmRentalComparable(
            lease_start=row["lease_start"],
            building_name=str(row.get("building_name") or ""),
            unit_number=str(row.get("unit_number") or "").strip() or None,
            unit_series=_unit_series(str(row.get("unit_number") or "")),
            unit_match_status=str(row.get("unit_match_status") or "unresolved"),
            property_type=str(row.get("property_type") or ""),
            bedrooms=str(row.get("bedrooms") or ""),
            size_sqft=float(row.get("size_sqft") or 0),
            annual_rent_aed=int(row.get("annual_rent_aed") or 0),
            rent_per_sqft_aed=(
                round(
                    int(row.get("annual_rent_aed") or 0) / float(row.get("size_sqft") or 1),
                    2,
                )
                if row.get("size_sqft")
                else None
            ),
            selection_reason=selection_reason,
        )
        for row, selection_reason in selected_rental_rows
    ]

    sale_psf = [
        float(comp.price_per_sqft_aed or comp.sale_amount_aed / comp.size_sqft)
        for comp in sale_comps
        if comp.size_sqft
    ]
    rent_psf = [
        float(comp.rent_per_sqft_aed) for comp in rental_comps if comp.rent_per_sqft_aed is not None
    ]
    median_sale_psf = _percentile(sale_psf, 0.5)
    low_sale_psf = _percentile(sale_psf, 0.25)
    high_sale_psf = _percentile(sale_psf, 0.75)
    median_rent_psf = _percentile(rent_psf, 0.5)
    estimated_value = int(round(median_sale_psf * size)) if median_sale_psf and size else None
    estimated_low = int(round(low_sale_psf * size)) if low_sale_psf and size else None
    estimated_high = int(round(high_sale_psf * size)) if high_sale_psf and size else None
    estimated_rent = int(round(median_rent_psf * size)) if median_rent_psf and size else None
    purchase_price = lead.matched_sale_price_aed
    capital_change = (
        estimated_value - purchase_price if estimated_value and purchase_price else None
    )
    capital_change_pct = (
        round(capital_change / purchase_price * 100, 2)
        if capital_change is not None and purchase_price
        else None
    )
    selling_costs = int(round(estimated_value * 0.021 + 5_000)) if estimated_value else None
    proceeds_before_debt = (
        estimated_value - selling_costs
        if estimated_value is not None and selling_costs is not None
        else None
    )
    confidence = (
        "high"
        if len(sale_comps) >= 3 and len(rental_comps) >= 3
        else "medium"
        if len(sale_comps) >= 2 and len(rental_comps) >= 2
        else "low"
    )
    return CrmPropertyReportResponse(
        lead=lead,
        period_start=period_start,
        period_end=anchor,
        sales_comparables=sale_comps,
        rental_comparables=rental_comps,
        analysis=CrmReportAnalysis(
            estimated_market_value_aed=estimated_value,
            estimated_value_low_aed=estimated_low,
            estimated_value_high_aed=estimated_high,
            estimated_market_rent_aed=estimated_rent,
            indicated_capital_change_aed=capital_change,
            indicated_capital_change_pct=capital_change_pct,
            indicative_selling_costs_aed=selling_costs,
            indicative_proceeds_before_debt_aed=proceeds_before_debt,
            estimated_market_gross_yield_pct=(
                round(estimated_rent / estimated_value * 100, 2)
                if estimated_rent and estimated_value
                else None
            ),
            current_rent_vs_market_pct=(
                round((lead.annual_rent_aed - estimated_rent) / estimated_rent * 100, 2)
                if estimated_rent
                else None
            ),
            target_unit_series=_unit_series(lead.unit_number),
            sales_selection_basis=sales_basis,
            rental_selection_basis=rentals_basis,
            sales_comparables_used=len(sale_comps),
            rental_comparables_used=len(rental_comps),
            confidence=confidence,
        ),
        price_index=price_index,
        agent_signals=_agent_signals(lead),
        methodology=[
            "Comparable window: the 365 days ending on the report date.",
            f"Sales cohort: {sales_basis}",
            f"Rental cohort: {rentals_basis}",
            "Indicated value uses median comparable sale price per sqft; the range uses "
            "the 25th and 75th percentiles.",
            "Indicative selling costs assume 2.1% of value plus AED 5,000 administration. "
            "Mortgage settlement, NOC, conveyancing, and property-specific costs are excluded.",
            "Any LTV shown is the ratio reported at purchase and is not a current loan balance.",
            price_index.methodology,
        ],
        generated_at=datetime.now(timezone.utc),
    )


def _empty_dashboard(anchor: date, limit: int, offset: int, breakdown: str) -> CrmDashboardResponse:
    return CrmDashboardResponse(
        leads=[],
        total=0,
        limit=limit,
        offset=offset,
        summary=CrmSummary(
            total_leads=0,
            urgent=0,
            expired_unlet=0,
            expiring_30_days=0,
            expiring_31_to_60_days=0,
            expiring_61_to_90_days=0,
            sale_conversation_candidates=0,
            annual_rent_at_risk_aed=0,
        ),
        breakdown=[],
        breakdown_level=breakdown,
        filters=CrmFilters(),
        coverage=CrmCoverage(
            rental_source="Lease transaction registry",
            matching_method="Awaiting normalized rental events",
            caveat="Load the normalized rental snapshot before using lead inference.",
        ),
        as_of=anchor,
    )
