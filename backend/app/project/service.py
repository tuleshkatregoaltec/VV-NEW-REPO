"""Project and building services - redesigned for ClickHouse from first principles."""

import asyncio
import json
import logging
import math
import re
import time
from bisect import bisect_left
from datetime import date
from typing import Any, List, Optional

from app.clickhouse.client import query
from app.core.market_constants import SQM_TO_SQFT
from app.core.normalization import (
    DEVELOPER_LEGAL_ENTITY_PATTERN,
    developer_brand_name,
    developer_filter_names,
)
from app.core.reelly_scope import reelly_dubai_project_scope
from app.project.models import (
    BuildingDetailResponse,
    BuildingInfo,
    BuildingUnitType,
    DDAOutlineFeature,
    DDAPlotFeature,
    GeoPin,
    GeoPolygon,
    MasterProjectResponse,
    MasterProjectSummary,
    ProjectDetailResponse,
    ProjectMarketSnapshotResponse,
    ProjectRadarArea,
    ProjectRadarOverviewResponse,
    ProjectRadarProject,
    ProjectRadarResponse,
    ProjectRadarStats,
    ProjectSearchResult,
    ProjectUnitComposition,
    RadarBuildingPin,
)

logger = logging.getLogger(__name__)

DDA_GEOMETRY_CACHE_TTL_SECONDS = 60 * 60
_dda_geometry_cache: tuple[float, list[dict[str, Any]]] | None = None
DDA_VILLA_MAX_PLOT_AREA_SQM = 2_500
DDA_VILLA_SUBDIVISION_MIN_PLOTS = 5
DDA_VALUATION_LOOKBACK_DAYS = 365 * 5
DDA_VALUATION_MIN_TRANSACTION_AED = 1_000_000
DDA_VALUATION_MARKET_PROCEDURES = (
    "Sell",
    "Delayed Sell",
    "Sale On Payment Plan",
)
DDA_VALUATION_MAX_PLOT_AREA_DELTA = 0.01
DDA_VALUATION_MIN_COMP_COUNT = 3
DDA_VALUATION_SIZE_BAND = (0.5, 1.75)
RADAR_YIELD_MIN_SAMPLE_COUNT = 5
RADAR_YIELD_MIN_PCT = 1
RADAR_YIELD_MAX_PCT = 25
RADAR_ACTIVITY_PERIODS = frozenset({30, 90, 180, 365})
CH_GEO_BUILDINGS_SOURCE = "ch_geo_buildings"
REELLY_PROJECT_ID_OFFSET = 9_000_000_000_000


def _room_sort_key(rooms: str) -> tuple:
    normalized = rooms.strip()
    if normalized.lower() == "studio":
        return (0, 0, normalized)
    match = re.match(r"^(\d+)", normalized)
    if match:
        return (1, int(match.group(1)), normalized)
    return (2, 0, normalized.lower())


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _date_or_none(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.date() if hasattr(value, "date") else value
    return None


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _radar_gross_yield_pct(row: dict[str, Any]) -> float | None:
    """Compute yield with the same existing-sale denominator used by analytics."""
    sale_count = _int_value(row.get("yield_existing_sale_count"))
    rent_count = _int_value(row.get("yield_rental_contract_count"))
    median_price = _float_or_none(row.get("yield_existing_median_sale_price"))
    median_rent = _float_or_none(row.get("yield_median_annual_rent"))
    if (
        sale_count < RADAR_YIELD_MIN_SAMPLE_COUNT
        or rent_count < RADAR_YIELD_MIN_SAMPLE_COUNT
        or not median_price
        or not median_rent
    ):
        fact_yield = _float_or_none(row.get("gross_yield_pct"))
        if fact_yield is not None and RADAR_YIELD_MIN_PCT <= fact_yield <= RADAR_YIELD_MAX_PCT:
            return round(fact_yield, 2)
        return None

    yield_pct = round(median_rent / median_price * 100, 2)
    if yield_pct < RADAR_YIELD_MIN_PCT or yield_pct > RADAR_YIELD_MAX_PCT:
        return None
    return yield_pct


def _contains_arabic(value: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in value)


def _developer_lookup(rows: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in rows:
        english = str(row.get("developer_name_en") or "").strip()
        arabic = str(row.get("developer_name_ar") or "").strip()
        if english:
            lookup[english] = english
        if arabic and english:
            lookup[arabic] = english
    return lookup


def _developer_display_name(name: Any, lookup: dict[str, str]) -> str | None:
    label = str(name or "").strip()
    if not label:
        return None
    mapped = lookup.get(label)
    if mapped:
        return developer_brand_name(mapped)
    if _contains_arabic(label):
        return None
    branded = developer_brand_name(label)
    if branded == label and DEVELOPER_LEGAL_ENTITY_PATTERN.search(branded):
        return None
    return branded


def _developer_display_list(raw: Any, lookup: dict[str, str], *, limit: int = 5) -> list[str]:
    if not isinstance(raw, list):
        return []
    labels: list[str] = []
    for item in raw:
        label = _developer_display_name(item, lookup)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _land_use_labels(raw: Any, limit: int = 3) -> list[str]:
    if raw in (None, "", []):
        return []

    if isinstance(raw, list):
        labels: list[str] = []
        for item in raw:
            labels.extend(_land_use_labels(item, limit=limit))
            if len(labels) >= limit:
                break
        return labels[:limit]

    if not isinstance(raw, str):
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip()
        return [cleaned] if cleaned else []

    labels = []
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            label = " ".join(
                str(item.get(key) or "").strip()
                for key in ("type", "use")
                if str(item.get(key) or "").strip()
            )
            if label and label not in labels:
                labels.append(label)
            if len(labels) >= limit:
                break
    return labels


def _radar_geo_cte() -> str:
    return f"""
    legacy_geo_by_project AS (
        SELECT
            lowerUTF8(trim(gb.project_name_en)) AS project_key,
            replaceRegexpAll(lowerUTF8(gb.project_name_en), '[^a-z0-9]', '')
                AS normalized_project_key,
            min(gb.property_id) AS property_id,
            any(gb.project_name_en) AS project_name_en,
            any(gb.area_name_en) AS area_name_en,
            any(gb.developer_name) AS developer_name,
            avg(gb.lat) AS legacy_latitude,
            avg(gb.lng) AS legacy_longitude,
            count() AS geo_pin_count,
            count() AS building_point_count
        FROM ch_geo_buildings AS gb
        WHERE gb.project_name_en != ''
          AND gb.lat BETWEEN 20 AND 30
          AND gb.lng BETWEEN 50 AND 60
        GROUP BY project_key, normalized_project_key
    ),
    unique_pf_project_coordinates AS (
        SELECT
            candidate.normalized_name AS normalized_project_key,
            any(candidate.latitude) AS candidate_latitude,
            any(candidate.longitude) AS candidate_longitude
        FROM geo_location_nodes AS candidate
        WHERE candidate.location_type IN ('TOWER', 'SUBCOMMUNITY')
          AND candidate.normalized_name != ''
          AND candidate.latitude BETWEEN 24 AND 26
          AND candidate.longitude BETWEEN 54 AND 57
        GROUP BY candidate.normalized_name
        HAVING uniqExact(candidate.canonical_location_id) = 1
    ),
    reelly_catalogue_projects AS (
        SELECT
            lowerUTF8(trim(project_name)) AS project_key,
            replaceRegexpAll(lowerUTF8(project_name), '[^a-z0-9]', '')
                AS normalized_project_key,
            {REELLY_PROJECT_ID_OFFSET} + toUInt64(project_id) AS property_id,
            any(project_name) AS project_name_en,
            any(area_name) AS area_name_en,
            any(developer_name) AS developer_name,
            any(latitude) AS reelly_latitude,
            any(longitude) AS reelly_longitude,
            any(sale_status) AS supply_status,
            any(completion_time) AS supply_completion_time,
            any(units_in_sale) AS units_in_sale,
            any(readiness_progress) AS supply_readiness
        FROM silver_reelly_projects FINAL
        WHERE project_name != ''
          AND {reelly_dubai_project_scope()}
          AND latitude BETWEEN 24 AND 26
          AND longitude BETWEEN 54 AND 57
          AND toUInt64OrZero(project_id) > 0
        GROUP BY project_key, normalized_project_key, property_id
        HAVING uniqExact(project_id) = 1
    ),
    geo_candidates AS (
        SELECT
            lg.project_key AS project_key,
            lg.normalized_project_key AS normalized_project_key,
            lg.property_id AS property_id,
            lg.project_name_en AS project_name_en,
            lg.area_name_en AS area_name_en,
            lg.developer_name AS developer_name,
            lg.legacy_latitude AS legacy_latitude,
            lg.legacy_longitude AS legacy_longitude,
            lg.geo_pin_count AS geo_pin_count,
            lg.building_point_count AS building_point_count,
            pf.candidate_latitude AS pf_latitude,
            pf.candidate_longitude AS pf_longitude,
            reelly.reelly_latitude AS reelly_latitude,
            reelly.reelly_longitude AS reelly_longitude,
            if(
                pf.candidate_latitude IS NOT NULL AND pf.candidate_longitude IS NOT NULL,
                greatCircleDistance(
                    lg.legacy_longitude,
                    lg.legacy_latitude,
                    pf.candidate_longitude,
                    pf.candidate_latitude
                ),
                1000000000
            ) AS pf_distance_m,
            if(
                reelly.reelly_latitude IS NOT NULL
                AND reelly.reelly_longitude IS NOT NULL,
                greatCircleDistance(
                    lg.legacy_longitude,
                    lg.legacy_latitude,
                    reelly.reelly_longitude,
                    reelly.reelly_latitude
                ),
                1000000000
            ) AS reelly_distance_m,
            if(
                pf.candidate_latitude IS NOT NULL
                AND pf.candidate_longitude IS NOT NULL
                AND reelly.reelly_latitude IS NOT NULL
                AND reelly.reelly_longitude IS NOT NULL,
                greatCircleDistance(
                    pf.candidate_longitude,
                    pf.candidate_latitude,
                    reelly.reelly_longitude,
                    reelly.reelly_latitude
                ),
                1000000000
            ) AS source_spread_m
        FROM legacy_geo_by_project AS lg
        LEFT JOIN unique_pf_project_coordinates AS pf
            ON pf.normalized_project_key = lg.normalized_project_key
        LEFT JOIN reelly_catalogue_projects AS reelly
            ON reelly.normalized_project_key = lg.normalized_project_key
    ),
    resolved_legacy_projects AS (
        SELECT
            project_key,
            normalized_project_key,
            property_id,
            project_name_en,
            area_name_en,
            developer_name,
            multiIf(
                pf_distance_m <= 2000, pf_latitude,
                reelly_distance_m <= 2000, reelly_latitude,
                legacy_latitude
            ) AS latitude,
            multiIf(
                pf_distance_m <= 2000, pf_longitude,
                reelly_distance_m <= 2000, reelly_longitude,
                legacy_longitude
            ) AS longitude,
            geo_pin_count,
            multiIf(
                pf_distance_m <= 2000 AND reelly_distance_m <= 2000 AND source_spread_m <= 500,
                    'pf_reelly_consensus',
                pf_distance_m <= 2000, 'pf_location_hierarchy',
                reelly_distance_m <= 2000, 'reelly_catalogue',
                '{CH_GEO_BUILDINGS_SOURCE}'
            ) AS coordinate_source,
            multiIf(
                pf_distance_m <= 2000 AND reelly_distance_m <= 2000 AND source_spread_m <= 500,
                    'unique_name_distance_consensus',
                pf_distance_m <= 2000, 'unique_pf_name_within_2km',
                reelly_distance_m <= 2000, 'unique_reelly_name_within_2km',
                'building_centroid_fallback'
            ) AS coordinate_method,
            toUInt64(pf_distance_m <= 2000) + toUInt64(reelly_distance_m <= 2000)
                AS detail_point_count,
            building_point_count,
            0 AS land_point_count,
            'legacy_project' AS entity_source,
            '' AS supply_status,
            CAST(NULL, 'Nullable(DateTime)') AS supply_completion_time,
            toUInt32(0) AS units_in_sale,
            CAST(NULL, 'Nullable(Float64)') AS supply_readiness
        FROM geo_candidates
    ),
    reelly_geo_projects AS (
        SELECT
            reelly.project_key AS project_key,
            reelly.normalized_project_key AS normalized_project_key,
            reelly.property_id AS property_id,
            reelly.project_name_en AS project_name_en,
            reelly.area_name_en AS area_name_en,
            reelly.developer_name AS developer_name,
            if(
                pf.candidate_latitude IS NOT NULL
                AND pf.candidate_longitude IS NOT NULL
                AND greatCircleDistance(
                    reelly.reelly_longitude,
                    reelly.reelly_latitude,
                    pf.candidate_longitude,
                    pf.candidate_latitude
                ) <= 500,
                pf.candidate_latitude,
                reelly.reelly_latitude
            ) AS latitude,
            if(
                pf.candidate_latitude IS NOT NULL
                AND pf.candidate_longitude IS NOT NULL
                AND greatCircleDistance(
                    reelly.reelly_longitude,
                    reelly.reelly_latitude,
                    pf.candidate_longitude,
                    pf.candidate_latitude
                ) <= 500,
                pf.candidate_longitude,
                reelly.reelly_longitude
            ) AS longitude,
            toUInt64(1) AS geo_pin_count,
            if(
                pf.candidate_latitude IS NOT NULL
                AND pf.candidate_longitude IS NOT NULL
                AND greatCircleDistance(
                    reelly.reelly_longitude,
                    reelly.reelly_latitude,
                    pf.candidate_longitude,
                    pf.candidate_latitude
                ) <= 500,
                'pf_reelly_consensus',
                'reelly_catalogue'
            ) AS coordinate_source,
            if(
                pf.candidate_latitude IS NOT NULL
                AND pf.candidate_longitude IS NOT NULL
                AND greatCircleDistance(
                    reelly.reelly_longitude,
                    reelly.reelly_latitude,
                    pf.candidate_longitude,
                    pf.candidate_latitude
                ) <= 500,
                'exact_name_within_500m',
                'reelly_project_coordinate'
            ) AS coordinate_method,
            toUInt64(1) + toUInt64(
                pf.candidate_latitude IS NOT NULL
                AND pf.candidate_longitude IS NOT NULL
                AND greatCircleDistance(
                    reelly.reelly_longitude,
                    reelly.reelly_latitude,
                    pf.candidate_longitude,
                    pf.candidate_latitude
                ) <= 500
            ) AS detail_point_count,
            ifNull(legacy.building_point_count, 0) AS building_point_count,
            0 AS land_point_count,
            'reelly_project' AS entity_source,
            reelly.supply_status AS supply_status,
            reelly.supply_completion_time AS supply_completion_time,
            reelly.units_in_sale AS units_in_sale,
            reelly.supply_readiness AS supply_readiness
        FROM reelly_catalogue_projects AS reelly
        LEFT JOIN unique_pf_project_coordinates AS pf
            ON pf.normalized_project_key = reelly.normalized_project_key
        LEFT JOIN legacy_geo_by_project AS legacy
            ON legacy.normalized_project_key = reelly.normalized_project_key
    ),
    geo_by_project AS (
        SELECT *
        FROM reelly_geo_projects
        UNION ALL
        SELECT legacy.*
        FROM resolved_legacy_projects AS legacy
        LEFT JOIN reelly_catalogue_projects AS reelly
            ON reelly.normalized_project_key = legacy.normalized_project_key
        WHERE reelly.property_id = 0
    )
    """


async def list_all_projects() -> List[ProjectSearchResult]:
    """Get all map-searchable Reelly and legacy projects."""
    sql = f"""
        WITH {_radar_geo_cte()}
        SELECT
            -toInt64(property_id) AS project_id,
            project_name_en,
            area_name_en,
            '' AS master_project_en,
            developer_name,
            latitude,
            longitude
        FROM geo_by_project
        ORDER BY project_name_en
        LIMIT 5000
    """

    result = await query(sql, {})

    return [
        ProjectSearchResult(
            project_id=p["project_id"],
            project_name=p["project_name_en"],
            area_name=p.get("area_name_en", "Unknown"),
            developer_name=p.get("developer_name") or None,
            master_project_en=p.get("master_project_en") or None,
            latitude=p["latitude"],
            longitude=p["longitude"],
        )
        for p in result
    ]


async def get_project_details(project_id: int) -> Optional[ProjectDetailResponse]:
    """Get full project details including buildings and unit composition."""
    # Radar/search synthetic ids are negative. Reelly ids occupy a reserved,
    # reversible range; smaller values remain legacy coordinate property ids.
    if project_id < 0:
        property_id = abs(project_id)
        if property_id >= REELLY_PROJECT_ID_OFFSET:
            reelly_id = property_id - REELLY_PROJECT_ID_OFFSET
            reelly_rows = await query(
                f"""
                SELECT
                    project_name,
                    area_name,
                    developer_name,
                    latitude,
                    longitude,
                    sale_status,
                    completion_time,
                    readiness_progress
                FROM silver_reelly_projects FINAL
                WHERE project_id = {{project_id:String}}
                  AND {reelly_dubai_project_scope()}
                  AND latitude BETWEEN 24 AND 26
                  AND longitude BETWEEN 54 AND 57
                LIMIT 1
                """,
                {"project_id": str(reelly_id)},
            )
            if not reelly_rows:
                return None
            reelly_project = reelly_rows[0]
            completion_time = reelly_project.get("completion_time")
            completion_date = (
                completion_time.date()
                if completion_time is not None and hasattr(completion_time, "date")
                else None
            )
            return ProjectDetailResponse(
                project_id=project_id,
                project_name=reelly_project["project_name"],
                project_number=str(reelly_id),
                master_project_en=None,
                area_id=None,
                area_name=reelly_project.get("area_name") or "Unknown",
                latitude=float(reelly_project["latitude"]),
                longitude=float(reelly_project["longitude"]),
                developer_id=None,
                developer_name=reelly_project.get("developer_name") or None,
                master_developer_id=None,
                master_developer_name=None,
                no_of_buildings=None,
                no_of_units=None,
                no_of_villas=None,
                no_of_lands=None,
                project_start_date=None,
                project_end_date=completion_date,
                completion_date=completion_date,
                percent_completed=_float_or_none(reelly_project.get("readiness_progress")),
                project_status=reelly_project.get("sale_status") or None,
                unit_composition=[],
                buildings=[],
                geo_pins=[],
            )

        geo_project_sql = """
            SELECT
                any(gb.project_name_en) AS project_name_en,
                any(gb.area_name_en) AS area_name_en,
                any(gb.developer_name) AS developer_name,
                avg(gb.lat) AS latitude,
                avg(gb.lng) AS longitude
            FROM ch_geo_buildings AS gb
            WHERE gb.property_id = {property_id:UInt64}
              AND gb.project_name_en != ''
            GROUP BY gb.property_id
        """
        geo_project_rows = await query(geo_project_sql, {"property_id": property_id})
        if not geo_project_rows:
            return None

        geo_project = geo_project_rows[0]
        geo_rows = await query(
            """
            SELECT property_id, building_name_en, project_name_en, lat, lng
            FROM ch_geo_buildings
            WHERE project_name_en = {project_name:String}
              AND lat BETWEEN 20 AND 30
              AND lng BETWEEN 50 AND 60
            ORDER BY building_name_en
            """,
            {"project_name": geo_project["project_name_en"]},
        )
        geo_pins = [
            GeoPin(
                building_name=row["building_name_en"] or f"Building {row['property_id']}",
                project_name=row["project_name_en"],
                latitude=float(row["lat"]),
                longitude=float(row["lng"]),
                property_id=int(row["property_id"]),
                point_type="building",
            )
            for row in geo_rows
        ]
        buildings = [
            BuildingInfo(
                property_id=int(row["property_id"]),
                building_number=None,
                building_name=row["building_name_en"] or f"Building {row['property_id']}",
                floors=None,
            )
            for row in geo_rows
        ]
        return ProjectDetailResponse(
            project_id=project_id,
            project_name=geo_project["project_name_en"],
            project_number=None,
            master_project_en=None,
            area_id=None,
            area_name=geo_project.get("area_name_en") or "Unknown",
            latitude=float(geo_project["latitude"]),
            longitude=float(geo_project["longitude"]),
            developer_id=None,
            developer_name=geo_project.get("developer_name") or None,
            master_developer_id=None,
            master_developer_name=None,
            no_of_buildings=len(buildings) or None,
            no_of_units=None,
            no_of_villas=None,
            no_of_lands=None,
            project_start_date=None,
            project_end_date=None,
            completion_date=None,
            percent_completed=None,
            project_status=None,
            unit_composition=[],
            buildings=buildings,
            geo_pins=geo_pins,
        )

    project_sql = """
        SELECT
            p.project_id AS project_id,
            p.project_number,
            p.project_name_en,
            p.master_project_en,
            p.area_id,
            p.area_name_en,
            p.developer_id,
            COALESCE(NULLIF(d1.developer_name_en, ''), p.developer_name) AS developer_name,
            p.master_developer_id,
            COALESCE(NULLIF(d2.developer_name_en, ''), p.master_developer_name) AS master_developer_name,
            p.no_of_buildings,
            p.no_of_units,
            p.no_of_villas,
            p.no_of_lands,
            p.project_start_date,
            p.project_end_date,
            p.completion_date,
            p.percent_completed,
            p.project_status,
            COALESCE(NULLIF(g.centroid_lat, 0), 25.2048) AS latitude,
            COALESCE(NULLIF(g.centroid_lng, 0), 55.2708) AS longitude,
            g.polygon AS area_polygon
        FROM ch_projects p
        LEFT JOIN ch_developers d1 ON p.developer_name = d1.developer_name_ar
        LEFT JOIN ch_developers d2 ON p.master_developer_name = d2.developer_name_ar
        LEFT JOIN ch_geo_projects g ON p.project_id = g.project_id
        WHERE p.project_id = {project_id:Int32}
        LIMIT 1
    """

    project_result = await query(project_sql, {"project_id": project_id})

    if not project_result:
        return None

    project = project_result[0]

    buildings_sql = """
        SELECT property_id, building_number, floors
        FROM ch_buildings
        WHERE project_id = {project_id:Int32}
        ORDER BY building_number
        LIMIT 100
    """

    composition_sql = """
        SELECT
            property_sub_type_en,
            count() as count,
            round(avg(actual_area), 2) as avg_area_sqm
        FROM ch_units
        WHERE project_id = {project_id:Int32}
          AND property_sub_type_en != ''
        GROUP BY property_sub_type_en
        ORDER BY count DESC
    """

    geo_sql = """
        SELECT building_name_en, project_name_en, lat, lng
        FROM ch_geo_buildings
        WHERE project_name_en = {project_name:String}
        ORDER BY building_name_en
    """

    query_tasks = [
        query(buildings_sql, {"project_id": project_id}),
        query(composition_sql, {"project_id": project_id}),
        query(geo_sql, {"project_name": project["project_name_en"]}),
    ]
    results = await asyncio.gather(*query_tasks)
    buildings_result = results[0]
    composition_result = results[1]
    geo_result = results[2]

    buildings = [
        BuildingInfo(
            property_id=b["property_id"],
            building_number=b.get("building_number") or None,
            building_name=b.get("building_number") or f"Building {b['property_id']}",
            floors=b.get("floors") or None,
        )
        for b in buildings_result
    ]

    unit_composition: List[ProjectUnitComposition] = []
    total_units = sum(row["count"] for row in composition_result)
    if total_units > 0:
        for row in composition_result:
            unit_composition.append(
                ProjectUnitComposition(
                    property_sub_type=row["property_sub_type_en"],
                    count=row["count"],
                    percentage=round((row["count"] / total_units) * 100, 2),
                    avg_area_sqm=float(row["avg_area_sqm"]) if row["avg_area_sqm"] else None,
                )
            )

    # Build normalized lookup: building name → property_id for geo pin matching
    def _norm(s: str) -> str:
        return "".join(c.lower() for c in s if c.isalnum())

    building_by_norm = {
        _norm(b.building_name or ""): b.property_id for b in buildings if b.building_name
    }

    geo_pins = [
        GeoPin(
            building_name=r["building_name_en"],
            project_name=r["project_name_en"],
            latitude=r["lat"],
            longitude=r["lng"],
            property_id=building_by_norm.get(_norm(r["building_name_en"])) or None,
            point_type="building",
        )
        for r in geo_result
    ]

    # Derive project center from geo pins when ch_geo_projects has no entry
    proj_lat = float(project["latitude"])
    proj_lng = float(project["longitude"])
    if proj_lat in (0.0, 25.2048) and geo_pins:
        proj_lat = sum(p.latitude for p in geo_pins) / len(geo_pins)
        proj_lng = sum(p.longitude for p in geo_pins) / len(geo_pins)

    raw_polygon = project.get("area_polygon") or []
    area_polygon = GeoPolygon(coordinates=raw_polygon) if raw_polygon else None

    return ProjectDetailResponse(
        project_id=project["project_id"],
        project_name=project["project_name_en"] or f"Project {project['project_id']}",
        project_number=project.get("project_number"),
        master_project_en=project.get("master_project_en") or None,
        area_id=project.get("area_id"),
        area_name=project.get("area_name_en", "Unknown"),
        latitude=proj_lat,
        longitude=proj_lng,
        area_polygon=area_polygon,
        developer_id=project.get("developer_id"),
        developer_name=project.get("developer_name") or None,
        master_developer_id=project.get("master_developer_id"),
        master_developer_name=project.get("master_developer_name") or None,
        no_of_buildings=project.get("no_of_buildings"),
        no_of_units=project.get("no_of_units"),
        no_of_villas=project.get("no_of_villas"),
        no_of_lands=project.get("no_of_lands"),
        project_start_date=project.get("project_start_date"),
        project_end_date=project.get("project_end_date"),
        completion_date=project.get("completion_date"),
        percent_completed=project.get("percent_completed"),
        project_status=project.get("project_status"),
        unit_composition=unit_composition,
        buildings=buildings,
        geo_pins=geo_pins,
    )


async def get_master_project(master_name: str) -> Optional[MasterProjectResponse]:
    """Get aggregated data for a master project and all its sub-projects."""
    sub_projects_sql = """
        SELECT
            p.project_id,
            p.project_name_en,
            p.project_status,
            p.percent_completed,
            p.no_of_buildings,
            p.no_of_units,
            p.area_name_en,
            COALESCE(NULLIF(d.developer_name_en, ''), p.developer_name) AS developer_name
        FROM ch_projects p
        LEFT JOIN ch_developers d ON p.developer_name = d.developer_name_ar
        WHERE p.master_project_en = {name:String}
          AND p.project_name_en != ''
        ORDER BY p.project_name_en
    """
    sub_projects_result = await query(sub_projects_sql, {"name": master_name})

    if not sub_projects_result:
        return None

    project_names = [p["project_name_en"] for p in sub_projects_result]
    project_ids = [p["project_id"] for p in sub_projects_result]
    area_name = sub_projects_result[0].get("area_name_en", "Unknown")
    developer_name = sub_projects_result[0].get("developer_name") or None

    geo_sql = """
        SELECT building_name_en, project_name_en, lat, lng
        FROM ch_geo_buildings
        WHERE project_name_en IN {names:Array(String)}
        ORDER BY project_name_en, building_name_en
    """
    composition_sql = """
        SELECT
            property_sub_type_en,
            count() AS count,
            round(avg(actual_area), 2) AS avg_area_sqm
        FROM ch_units
        WHERE project_id IN {ids:Array(Int32)}
          AND property_sub_type_en != ''
        GROUP BY property_sub_type_en
        ORDER BY count DESC
    """

    geo_result, composition_result = await asyncio.gather(
        query(geo_sql, {"names": project_names}),
        query(composition_sql, {"ids": project_ids}),
    )

    geo_pins = [
        GeoPin(
            building_name=r["building_name_en"],
            project_name=r["project_name_en"],
            latitude=r["lat"],
            longitude=r["lng"],
        )
        for r in geo_result
    ]

    total_units_comp = sum(r["count"] for r in composition_result)
    unit_composition: List[ProjectUnitComposition] = []
    if total_units_comp > 0:
        for row in composition_result:
            unit_composition.append(
                ProjectUnitComposition(
                    property_sub_type=row["property_sub_type_en"],
                    count=row["count"],
                    percentage=round((row["count"] / total_units_comp) * 100, 2),
                    avg_area_sqm=float(row["avg_area_sqm"]) if row["avg_area_sqm"] else None,
                )
            )

    projects = [
        MasterProjectSummary(
            project_id=p["project_id"],
            project_name=p["project_name_en"],
            project_status=p.get("project_status") or None,
            percent_completed=p.get("percent_completed"),
            no_of_buildings=p.get("no_of_buildings"),
            no_of_units=p.get("no_of_units"),
        )
        for p in sub_projects_result
    ]

    total_buildings = sum((p.no_of_buildings or 0) for p in projects)
    total_units = sum((p.no_of_units or 0) for p in projects)

    return MasterProjectResponse(
        master_name=master_name,
        area_name=area_name,
        developer_name=developer_name,
        total_projects=len(projects),
        total_buildings=total_buildings,
        total_units=total_units,
        projects=projects,
        geo_pins=geo_pins,
        unit_composition=unit_composition,
    )


def _validated_radar_period_days(period_days: int) -> int:
    if period_days not in RADAR_ACTIVITY_PERIODS:
        raise ValueError("Radar activity period must be one of 30, 90, 180, or 365 days")
    return period_days


def _radar_source_notes(period_days: int) -> list[str]:
    return [
        f"Market activity uses detailed DLD sales and Ejari lease records for the trailing {period_days} days.",
        "Activity is anchored to the latest available record and never extends beyond one trailing year.",
        "Transaction locations use approved canonical geography links; coverage is shown with the map totals.",
        "Project pins include every geocoded Dubai Reelly project plus non-duplicate historical and secondary projects.",
        "The tower layer uses Property Finder's physical tower coordinates and only attaches exact, approved DLD/Ejari evidence.",
        "Small villa parcels may be marked probable when their enclosing subdivision has confirmed development evidence.",
    ]


def _radar_stats_from_row(row: dict[str, Any], period_days: int) -> ProjectRadarStats:
    sales_count = int(row.get("sales_transaction_count") or 0)
    rent_count = int(row.get("rental_contract_count") or 0)
    sales_volume = _float_or_none(row.get("total_sales_volume")) or 0.0
    return ProjectRadarStats(
        total_projects=int(row.get("total_projects") or 0),
        mapped_projects=int(row.get("mapped_projects") or 0),
        active_projects=int(row.get("active_projects") or 0),
        finished_projects=int(row.get("finished_projects") or 0),
        pipeline_units=int(row.get("pipeline_units") or 0),
        units_delivering_next_12_months=int(row.get("units_delivering_next_12_months") or 0),
        sales_transaction_count_12m=sales_count,
        rental_contract_count_12m=rent_count,
        total_sales_volume_12m=sales_volume,
        dda_plot_count=int(row.get("dda_plot_count") or 0),
        dda_total_plot_area_sqm=_float_or_none(row.get("dda_total_plot_area_sqm")) or 0.0,
        dda_total_gfa_sqm=_float_or_none(row.get("dda_total_gfa_sqm")) or 0.0,
        activity_period_days=period_days,
        activity_period_start=row.get("activity_period_start"),
        activity_period_end=row.get("activity_period_end"),
        sales_transaction_count=sales_count,
        rental_contract_count=rent_count,
        total_sales_volume=sales_volume,
        mapped_sales_transaction_count=int(row.get("mapped_sales_transaction_count") or 0),
        mapped_rental_contract_count=int(row.get("mapped_rental_contract_count") or 0),
        activity_coverage_pct=_float_or_none(row.get("activity_coverage_pct")) or 0.0,
    )


def _radar_projects_from_rows(
    rows: list[dict[str, Any]], developers: dict[str, str]
) -> list[ProjectRadarProject]:
    return [
        ProjectRadarProject(
            project_id=row["project_id"],
            project_name=row["project_name_en"],
            area_name=row.get("area_name_en") or "Unknown",
            developer_name=_developer_display_name(row.get("developer_name"), developers),
            master_project_en=row.get("master_project_en") or None,
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            geo_pin_count=int(row.get("geo_pin_count") or 0),
            coordinate_source=row.get("coordinate_source") or CH_GEO_BUILDINGS_SOURCE,
            coordinate_method=row.get("coordinate_method") or None,
            detail_point_count=int(row.get("detail_point_count") or 0),
            building_point_count=int(row.get("building_point_count") or 0),
            land_point_count=int(row.get("land_point_count") or 0),
            entity_source=row.get("entity_source") or "legacy_project",
            supply_status=row.get("supply_status") or None,
            supply_completion_date=_date_or_none(row.get("supply_completion_time")),
            units_in_sale=int(row.get("units_in_sale") or 0),
            completion_status=row.get("completion_status") or "",
            pipeline_status=row.get("pipeline_status") or "",
            project_status=row.get("project_status") or None,
            no_of_units=int(row.get("no_of_units") or 0),
            no_of_buildings=int(row.get("no_of_buildings") or 0),
            percent_completed=_float_or_none(row.get("percent_completed")),
            delivery_confidence=_float_or_none(row.get("estimated_delivery_confidence")) or 0.0,
            sales_transaction_count_12m=int(row.get("sales_transaction_count") or 0),
            rental_contract_count_12m=int(row.get("rental_contract_count") or 0),
            total_sales_volume_12m=_float_or_none(row.get("total_sales_volume")) or 0.0,
            median_sale_price=_float_or_none(row.get("median_sale_price")),
            median_annual_rent=_float_or_none(row.get("median_annual_rent")),
            gross_yield_pct=_radar_gross_yield_pct(row),
            avg_sale_price_sqm_12m=_float_or_none(row.get("avg_sale_price_sqm")),
            avg_rent_price_sqm_12m=_float_or_none(row.get("avg_rent_price_sqm")),
            sales_transaction_count=int(row.get("sales_transaction_count") or 0),
            rental_contract_count=int(row.get("rental_contract_count") or 0),
            total_sales_volume=_float_or_none(row.get("total_sales_volume")) or 0.0,
            avg_sale_price_sqm=_float_or_none(row.get("avg_sale_price_sqm")),
            avg_rent_price_sqm=_float_or_none(row.get("avg_rent_price_sqm")),
        )
        for row in rows
    ]


def _radar_areas_from_rows(
    rows: list[dict[str, Any]], developers: dict[str, str]
) -> list[ProjectRadarArea]:
    areas = [
        ProjectRadarArea(
            area_id=int(row.get("area_id") or 0),
            area_name=row.get("area_name_en") or "Unknown",
            latitude=_float_or_none(row.get("latitude")),
            longitude=_float_or_none(row.get("longitude")),
            mapped_projects=int(row.get("mapped_projects") or 0),
            active_projects=int(row.get("active_projects") or 0),
            completed_projects=int(row.get("completed_projects") or 0),
            overdue_projects=int(row.get("overdue_projects") or 0),
            pipeline_units=int(row.get("pipeline_units") or 0),
            units_delivering_next_12_months=int(row.get("units_delivering_next_12_months") or 0),
            active_developers=int(row.get("active_developers") or 0),
            avg_completion_pct=_float_or_none(row.get("avg_completion_pct")) or 0.0,
            avg_delivery_confidence=_float_or_none(row.get("avg_delivery_confidence")) or 0.0,
            sales_transaction_count_12m=int(row.get("sales_transaction_count") or 0),
            rental_contract_count_12m=int(row.get("rental_contract_count") or 0),
            total_sales_volume_12m=_float_or_none(row.get("total_sales_volume")) or 0.0,
            median_sale_price=_float_or_none(row.get("median_sale_price")),
            median_annual_rent=_float_or_none(row.get("median_annual_rent")),
            avg_sale_price_sqm_12m=_float_or_none(row.get("avg_sale_price_sqm")),
            avg_rent_price_sqm_12m=_float_or_none(row.get("avg_rent_price_sqm")),
            gross_yield_pct=_radar_gross_yield_pct(row),
            top_developers=_developer_display_list(row.get("top_developers"), developers, limit=5),
            top_master_projects=list(row.get("top_master_projects") or [])[:5],
            dda_plot_count=int(row.get("dda_plot_count") or 0),
            dda_total_plot_area_sqm=_float_or_none(row.get("dda_total_plot_area_sqm")) or 0.0,
            dda_total_gfa_sqm=_float_or_none(row.get("dda_total_gfa_sqm")) or 0.0,
            dda_dominant_land_uses=_land_use_labels(row.get("dda_dominant_land_uses"), limit=5),
            sales_transaction_count=int(row.get("sales_transaction_count") or 0),
            rental_contract_count=int(row.get("rental_contract_count") or 0),
            total_sales_volume=_float_or_none(row.get("total_sales_volume")) or 0.0,
            avg_sale_price_sqm=_float_or_none(row.get("avg_sale_price_sqm")),
            avg_rent_price_sqm=_float_or_none(row.get("avg_rent_price_sqm")),
        )
        for row in rows
    ]
    unique_areas: list[ProjectRadarArea] = []
    seen_area_names: set[str] = set()
    for area in areas:
        area_key = area.area_name.strip().lower()
        if area_key in seen_area_names:
            continue
        seen_area_names.add(area_key)
        unique_areas.append(area)
    return unique_areas


def _radar_developer_lookup_sql() -> str:
    return """
        SELECT developer_name_ar, developer_name_en
        FROM ch_developers
        WHERE developer_name_en != ''
    """


def _radar_stats_sql(radar_geo_cte: str) -> str:
    return f"""
        WITH {radar_geo_cte},
        activity_anchor AS (
            SELECT greatest(
                (SELECT max(transaction_date)
                 FROM dxbi_sales_unit_events FINAL
                 WHERE transaction_date <= today()),
                (SELECT max(lease_start)
                 FROM dxbi_rental_events FINAL
                 WHERE lease_start <= today())
            ) AS period_end
        ),
        sales_activity AS (
            SELECT
                count() AS sales_transaction_count,
                sum(sale_amount_aed) AS total_sales_volume
            FROM dxbi_sales_unit_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            WHERE e.transaction_date > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.transaction_date <= a.period_end
        ),
        rental_activity AS (
            SELECT count() AS rental_contract_count
            FROM dxbi_rental_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            WHERE e.lease_start > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.lease_start <= a.period_end
        ),
        mapped_sales_activity AS (
            SELECT count() AS mapped_sales_transaction_count
            FROM dxbi_sales_unit_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            INNER JOIN geo_mapped_source_facts AS gm
                ON gm.source_system = 'dxbi_sales'
               AND gm.raw_area_name = e.area_name
               AND gm.raw_project_name = e.project_name
               AND gm.raw_building_name = e.building_name
               AND gm.property_type = e.property_type
               AND gm.market_status = e.market_status
               AND gm.source_grain = multiIf(
                    lowerUTF8(e.market_status) = 'offplan', 'project',
                    e.property_type IN ('Villa', 'Townhouse'), 'landed_phase',
                    e.building_name != '', 'building',
                    e.project_name != '', 'project',
                    'area'
               )
            WHERE gm.match_status IN ('auto_approved', 'manual_approved')
              AND e.transaction_date > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.transaction_date <= a.period_end
        ),
        mapped_rental_activity AS (
            SELECT count() AS mapped_rental_contract_count
            FROM dxbi_rental_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            INNER JOIN geo_mapped_source_facts AS gm
                ON gm.source_system = 'dxbi_rentals'
               AND gm.raw_area_name = e.area_name
               AND gm.raw_project_name = e.project_name
               AND gm.raw_building_name = e.building_name
               AND gm.property_type = e.property_type
               AND gm.market_status = ''
               AND gm.source_grain = multiIf(
                    e.property_type IN ('Villa', 'Townhouse'), 'landed_phase',
                    e.building_name != '', 'building',
                    e.project_name != '', 'project',
                    'area'
               )
            WHERE gm.match_status IN ('auto_approved', 'manual_approved')
              AND e.lease_start > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.lease_start <= a.period_end
        ),
        dda_stats AS (
            SELECT
                count() AS dda_plot_count,
                sum(plot_area_sqm) AS dda_total_plot_area_sqm,
                sum(max_gfa_sqm) AS dda_total_gfa_sqm
            FROM dda_land_plots
        )
        SELECT
            (SELECT countDistinct(property_id) FROM geo_by_project) AS total_projects,
            (SELECT countDistinct(property_id) FROM geo_by_project) AS mapped_projects,
            countIf(
                lowerUTF8(completion_status) NOT LIKE '%complete%'
                AND lowerUTF8(completion_status) NOT LIKE '%finish%'
                AND lowerUTF8(completion_status) NOT LIKE '%cancel%'
            ) AS active_projects,
            countIf(
                lowerUTF8(completion_status) LIKE '%complete%'
                OR lowerUTF8(completion_status) LIKE '%finish%'
            ) AS finished_projects,
            sumIf(
                no_of_units,
                lowerUTF8(completion_status) NOT LIKE '%complete%'
                AND lowerUTF8(completion_status) NOT LIKE '%finish%'
                AND lowerUTF8(completion_status) NOT LIKE '%cancel%'
            ) AS pipeline_units,
            sumIf(
                no_of_units,
                lowerUTF8(completion_status) NOT LIKE '%complete%'
                AND lowerUTF8(completion_status) NOT LIKE '%finish%'
                AND lowerUTF8(completion_status) NOT LIKE '%cancel%'
                AND project_end_date IS NOT NULL
                AND toDate(project_end_date) BETWEEN today() AND today() + INTERVAL 365 DAY
            ) AS units_delivering_next_12_months,
            any(sa.sales_transaction_count) AS sales_transaction_count,
            any(ra.rental_contract_count) AS rental_contract_count,
            any(sa.total_sales_volume) AS total_sales_volume,
            any(msa.mapped_sales_transaction_count) AS mapped_sales_transaction_count,
            any(mra.mapped_rental_contract_count) AS mapped_rental_contract_count,
            round(
                100 * (
                    any(msa.mapped_sales_transaction_count)
                    + any(mra.mapped_rental_contract_count)
                ) / greatest(
                    1,
                    any(sa.sales_transaction_count) + any(ra.rental_contract_count)
                ),
                1
            ) AS activity_coverage_pct,
            any(ds.dda_plot_count) AS dda_plot_count,
            any(ds.dda_total_plot_area_sqm) AS dda_total_plot_area_sqm,
            any(ds.dda_total_gfa_sqm) AS dda_total_gfa_sqm,
            any(a.period_end) - toIntervalDay({{period_days:UInt16}}) AS activity_period_start,
            any(a.period_end) AS activity_period_end
        FROM ch_project_fact
        CROSS JOIN activity_anchor AS a
        CROSS JOIN sales_activity AS sa
        CROSS JOIN rental_activity AS ra
        CROSS JOIN mapped_sales_activity AS msa
        CROSS JOIN mapped_rental_activity AS mra
        CROSS JOIN dda_stats AS ds
    """


def _radar_area_sql(radar_geo_cte: str) -> str:
    return f"""
        WITH {radar_geo_cte},
        activity_anchor AS (
            SELECT greatest(
                (SELECT max(transaction_date)
                 FROM dxbi_sales_unit_events FINAL
                 WHERE transaction_date <= today()),
                (SELECT max(lease_start)
                 FROM dxbi_rental_events FINAL
                 WHERE lease_start <= today())
            ) AS period_end
        ),
        location_community AS (
            SELECT
                c.descendant_location_id,
                argMin(c.ancestor_location_id, c.depth) AS community_location_id
            FROM geo_location_closure AS c
            INNER JOIN geo_location_nodes AS n
                ON n.canonical_location_id = c.ancestor_location_id
            WHERE n.location_type = 'COMMUNITY'
            GROUP BY c.descendant_location_id
        ),
        unique_pf_project_nodes AS (
            SELECT
                candidate.normalized_name,
                any(candidate.canonical_location_id) AS matched_location_id
            FROM geo_location_nodes AS candidate
            WHERE candidate.location_type IN ('TOWER', 'SUBCOMMUNITY')
              AND candidate.normalized_name != ''
            GROUP BY normalized_name
            HAVING uniqExact(candidate.canonical_location_id) = 1
        ),
        project_community_status AS (
            SELECT
                lc.community_location_id,
                count() AS mapped_projects,
                countIf(
                    lowerUTF8(pf.completion_status) NOT LIKE '%complete%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%finish%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%cancel%'
                ) AS active_projects,
                countIf(
                    lowerUTF8(pf.completion_status) LIKE '%complete%'
                    OR lowerUTF8(pf.completion_status) LIKE '%finish%'
                ) AS completed_projects,
                countIf(
                    lowerUTF8(pf.completion_status) LIKE '%delay%'
                    OR lowerUTF8(pf.completion_status) LIKE '%overdue%'
                    OR lowerUTF8(pf.completion_status) LIKE '%stall%'
                    OR lowerUTF8(pf.completion_status) LIKE '%suspend%'
                    OR lowerUTF8(pf.completion_status) LIKE '%hold%'
                ) AS overdue_projects,
                sumIf(
                    pf.no_of_units,
                    lowerUTF8(pf.completion_status) NOT LIKE '%complete%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%finish%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%cancel%'
                ) AS pipeline_units,
                sumIf(
                    pf.no_of_units,
                    lowerUTF8(pf.completion_status) NOT LIKE '%complete%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%finish%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%cancel%'
                    AND pf.project_end_date IS NOT NULL
                    AND toDate(pf.project_end_date) BETWEEN today() AND today() + INTERVAL 365 DAY
                ) AS units_delivering_next_12_months,
                uniqExactIf(
                    pf.developer_name,
                    pf.developer_name != ''
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%complete%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%finish%'
                    AND lowerUTF8(pf.completion_status) NOT LIKE '%cancel%'
                ) AS active_developers,
                avg(pf.percent_completed) AS avg_completion_pct,
                avg(pf.estimated_delivery_confidence) AS avg_delivery_confidence,
                arrayFilter(x -> x != '', topK(5)(pf.developer_name)) AS top_developers,
                arrayFilter(x -> x != '', topK(5)(pf.master_project_en)) AS top_master_projects
            FROM ch_project_fact AS pf
            INNER JOIN unique_pf_project_nodes AS pn
                ON pn.normalized_name = replaceRegexpAll(
                    lowerUTF8(pf.project_name_en),
                    '[^a-z0-9]',
                    ''
                )
            INNER JOIN location_community AS lc
                ON lc.descendant_location_id = pn.matched_location_id
            WHERE pf.project_name_en != ''
            GROUP BY lc.community_location_id
        ),
        sales_area_activity AS (
            SELECT
                lc.community_location_id,
                count() AS sales_transaction_count,
                sum(e.sale_amount_aed) AS total_sales_volume,
                quantile(0.5)(e.sale_amount_aed) AS median_sale_price,
                avgIf(
                    e.price_per_sqft_aed * {SQM_TO_SQFT},
                    e.price_per_sqft_aed IS NOT NULL AND e.price_per_sqft_aed > 0
                ) AS avg_sale_price_sqm
            FROM dxbi_sales_unit_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            INNER JOIN geo_mapped_source_facts AS gm
                ON gm.source_system = 'dxbi_sales'
               AND gm.raw_area_name = e.area_name
               AND gm.raw_project_name = e.project_name
               AND gm.raw_building_name = e.building_name
               AND gm.property_type = e.property_type
               AND gm.market_status = e.market_status
               AND gm.source_grain = multiIf(
                    lowerUTF8(e.market_status) = 'offplan', 'project',
                    e.property_type IN ('Villa', 'Townhouse'), 'landed_phase',
                    e.building_name != '', 'building',
                    e.project_name != '', 'project',
                    'area'
               )
            INNER JOIN location_community AS lc
                ON lc.descendant_location_id = gm.canonical_location_id
            WHERE gm.match_status IN ('auto_approved', 'manual_approved')
              AND e.transaction_date > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.transaction_date <= a.period_end
            GROUP BY lc.community_location_id
        ),
        rental_area_activity AS (
            SELECT
                lc.community_location_id,
                count() AS rental_contract_count,
                quantile(0.5)(e.annual_rent_aed) AS median_annual_rent,
                avgIf(
                    (e.annual_rent_aed / e.size_sqft) * {SQM_TO_SQFT},
                    e.annual_rent_aed > 0 AND e.size_sqft > 0
                ) AS avg_rent_price_sqm
            FROM dxbi_rental_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            INNER JOIN geo_mapped_source_facts AS gm
                ON gm.source_system = 'dxbi_rentals'
               AND gm.raw_area_name = e.area_name
               AND gm.raw_project_name = e.project_name
               AND gm.raw_building_name = e.building_name
               AND gm.property_type = e.property_type
               AND gm.market_status = ''
               AND gm.source_grain = multiIf(
                    e.property_type IN ('Villa', 'Townhouse'), 'landed_phase',
                    e.building_name != '', 'building',
                    e.project_name != '', 'project',
                    'area'
               )
            INNER JOIN location_community AS lc
                ON lc.descendant_location_id = gm.canonical_location_id
            WHERE gm.match_status IN ('auto_approved', 'manual_approved')
              AND e.lease_start > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.lease_start <= a.period_end
            GROUP BY lc.community_location_id
        ),
        area_geo AS (
            SELECT
                lowerUTF8(trim(g.area_name_en)) AS area_key,
                countDistinct(g.project_key) AS mapped_projects
            FROM geo_by_project g
            GROUP BY area_key
        ),
        area_status AS (
            SELECT
                lowerUTF8(trim(area_name_en)) AS area_key,
                any(area_id) AS area_id,
                countIf(
                    NOT (
                        upperUTF8(completion_status) IN ('FINISHED', 'COMPLETED')
                        OR lowerUTF8(completion_status) LIKE '%complete%'
                        OR lowerUTF8(completion_status) LIKE '%cancel%'
                    )
                ) AS active_projects,
                countIf(
                    upperUTF8(completion_status) IN ('FINISHED', 'COMPLETED')
                    OR lowerUTF8(completion_status) LIKE '%complete%'
                ) AS completed_projects,
                countIf(
                    lowerUTF8(completion_status) LIKE '%delay%'
                    OR lowerUTF8(completion_status) LIKE '%overdue%'
                    OR lowerUTF8(completion_status) LIKE '%stall%'
                    OR lowerUTF8(completion_status) LIKE '%suspend%'
                    OR lowerUTF8(completion_status) LIKE '%hold%'
                ) AS overdue_projects,
                sumIf(
                    no_of_units,
                    NOT (
                        upperUTF8(completion_status) IN ('FINISHED', 'COMPLETED')
                        OR lowerUTF8(completion_status) LIKE '%complete%'
                        OR lowerUTF8(completion_status) LIKE '%cancel%'
                    )
                ) AS pipeline_units,
                sumIf(
                    no_of_units,
                    NOT (
                        upperUTF8(completion_status) IN ('FINISHED', 'COMPLETED')
                        OR lowerUTF8(completion_status) LIKE '%complete%'
                        OR lowerUTF8(completion_status) LIKE '%cancel%'
                    )
                    AND project_end_date IS NOT NULL
                    AND toDate(project_end_date) BETWEEN today() AND today() + INTERVAL 365 DAY
                ) AS units_delivering_next_12_months,
                uniqExactIf(
                    developer_name,
                    developer_name != ''
                    AND NOT (
                        upperUTF8(completion_status) IN ('FINISHED', 'COMPLETED')
                        OR lowerUTF8(completion_status) LIKE '%complete%'
                        OR lowerUTF8(completion_status) LIKE '%cancel%'
                    )
                ) AS active_developers
                ,avg(percent_completed) AS avg_completion_pct
                ,avg(estimated_delivery_confidence) AS avg_delivery_confidence
                ,arrayFilter(x -> x != '', topK(5)(developer_name)) AS top_developers
                ,arrayFilter(x -> x != '', topK(5)(master_project_en)) AS top_master_projects
            FROM ch_project_fact
            WHERE area_name_en != ''
            GROUP BY area_key
        ),
        dda_area AS (
            SELECT
                lowerUTF8(trim(community_name)) AS area_key,
                count() AS dda_plot_count,
                sum(plot_area_sqm) AS dda_total_plot_area_sqm,
                sum(max_gfa_sqm) AS dda_total_gfa_sqm,
                arrayFilter(x -> x != '', topK(5)(land_use)) AS dda_dominant_land_uses
            FROM dda_land_plots
            WHERE community_name != ''
            GROUP BY area_key
        )
        SELECT
            toInt64OrZero(n.source_location_id) AS area_id,
            n.name AS area_name_en,
            n.latitude AS latitude,
            n.longitude AS longitude,
            ifNull(pcs.mapped_projects, ifNull(ag.mapped_projects, 0)) AS mapped_projects,
            ifNull(pcs.active_projects, ifNull(ast.active_projects, 0)) AS active_projects,
            ifNull(pcs.completed_projects, ifNull(ast.completed_projects, 0)) AS completed_projects,
            ifNull(pcs.overdue_projects, ifNull(ast.overdue_projects, 0)) AS overdue_projects,
            ifNull(pcs.pipeline_units, ifNull(ast.pipeline_units, 0)) AS pipeline_units,
            ifNull(
                pcs.units_delivering_next_12_months,
                ifNull(ast.units_delivering_next_12_months, 0)
            ) AS units_delivering_next_12_months,
            ifNull(pcs.active_developers, ifNull(ast.active_developers, 0)) AS active_developers,
            ifNull(pcs.avg_completion_pct, ifNull(ast.avg_completion_pct, 0)) AS avg_completion_pct,
            ifNull(
                pcs.avg_delivery_confidence,
                ifNull(ast.avg_delivery_confidence, 0)
            ) AS avg_delivery_confidence,
            ifNull(sa.sales_transaction_count, 0) AS sales_transaction_count,
            ifNull(ra.rental_contract_count, 0) AS rental_contract_count,
            ifNull(sa.total_sales_volume, 0) AS total_sales_volume,
            sa.median_sale_price AS median_sale_price,
            ra.median_annual_rent AS median_annual_rent,
            if(
                sa.sales_transaction_count >= {RADAR_YIELD_MIN_SAMPLE_COUNT}
                AND ra.rental_contract_count >= {RADAR_YIELD_MIN_SAMPLE_COUNT}
                AND sa.median_sale_price > 0
                AND ra.median_annual_rent > 0,
                ra.median_annual_rent / sa.median_sale_price * 100,
                NULL
            ) AS gross_yield_pct,
            sa.avg_sale_price_sqm AS avg_sale_price_sqm,
            ra.avg_rent_price_sqm AS avg_rent_price_sqm,
            ifNull(pcs.top_developers, ifNull(ast.top_developers, [])) AS top_developers,
            ifNull(pcs.top_master_projects, ifNull(ast.top_master_projects, [])) AS top_master_projects,
            ifNull(da.dda_plot_count, 0) AS dda_plot_count,
            ifNull(da.dda_total_plot_area_sqm, 0) AS dda_total_plot_area_sqm,
            ifNull(da.dda_total_gfa_sqm, 0) AS dda_total_gfa_sqm,
            ifNull(da.dda_dominant_land_uses, []) AS dda_dominant_land_uses,
            ifNull(sa.sales_transaction_count, 0) AS yield_existing_sale_count,
            ifNull(ra.rental_contract_count, 0) AS yield_rental_contract_count,
            sa.median_sale_price AS yield_existing_median_sale_price,
            ra.median_annual_rent AS yield_median_annual_rent
        FROM geo_location_nodes AS n
        LEFT JOIN sales_area_activity AS sa
            ON sa.community_location_id = n.canonical_location_id
        LEFT JOIN rental_area_activity AS ra
            ON ra.community_location_id = n.canonical_location_id
        LEFT JOIN project_community_status AS pcs
            ON pcs.community_location_id = n.canonical_location_id
        LEFT JOIN area_geo AS ag
            ON ag.area_key = lowerUTF8(trim(n.name))
        LEFT JOIN area_status AS ast
            ON ast.area_key = lowerUTF8(trim(n.name))
        LEFT JOIN dda_area AS da
            ON da.area_key = lowerUTF8(trim(n.name))
        WHERE n.location_type = 'COMMUNITY'
          AND (
            sa.sales_transaction_count > 0
            OR ra.rental_contract_count > 0
            OR pcs.active_projects > 0
            OR ast.active_projects > 0
            OR da.dda_plot_count > 0
          )
        ORDER BY
            ifNull(sa.sales_transaction_count, 0) + ifNull(ra.rental_contract_count, 0) DESC,
            pipeline_units DESC
        LIMIT 160
    """


def _radar_project_pins_sql(radar_geo_cte: str, where_clause: str) -> str:
    return f"""
        WITH {radar_geo_cte},
        activity_anchor AS (
            SELECT greatest(
                (SELECT max(transaction_date)
                 FROM dxbi_sales_unit_events FINAL
                 WHERE transaction_date <= today()),
                (SELECT max(lease_start)
                 FROM dxbi_rental_events FINAL
                 WHERE lease_start <= today())
            ) AS period_end
        ),
        fact_by_project AS (
            SELECT
                replaceRegexpAll(lowerUTF8(pf.project_name_en), '[^a-z0-9]', '') AS project_key,
                any(pf.project_name_en) AS project_name_en,
                any(pf.area_name_en) AS area_name_en,
                any(pf.developer_name) AS developer_name,
                any(pf.master_project_en) AS master_project_en,
                any(pf.completion_status) AS completion_status,
                any(pf.pipeline_status) AS pipeline_status,
                any(pf.project_status) AS project_status,
                any(pf.no_of_units) AS no_of_units,
                any(pf.no_of_buildings) AS no_of_buildings,
                any(pf.percent_completed) AS percent_completed,
                any(pf.estimated_delivery_confidence) AS estimated_delivery_confidence
            FROM ch_project_fact AS pf
            WHERE pf.project_name_en != ''
            GROUP BY project_key
        ),
        sales_by_project AS (
            SELECT
                if(
                    lowerUTF8(e.market_status) = 'offplan'
                    AND orm.match_status IN ('auto_approved', 'manual_approved')
                    AND orm.normalized_reelly_project_name != '',
                    orm.normalized_reelly_project_name,
                    replaceRegexpAll(
                        lowerUTF8(trim(if(
                            lowerUTF8(e.market_status) = 'offplan' AND e.building_name != '',
                            e.building_name,
                            e.project_name
                        ))),
                        '[^a-z0-9]',
                        ''
                    )
                ) AS project_key,
                count() AS sales_transaction_count,
                sum(sale_amount_aed) AS total_sales_volume,
                quantile(0.5)(sale_amount_aed) AS median_sale_price,
                avgIf(
                    price_per_sqft_aed * {SQM_TO_SQFT},
                    price_per_sqft_aed IS NOT NULL AND price_per_sqft_aed > 0
                ) AS avg_sale_price_sqm
            FROM dxbi_sales_unit_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            LEFT JOIN offplan_reelly_mapped_source_facts AS orm
                ON orm.source_system = 'dxbi_sales'
               AND orm.raw_area_name = e.area_name
               AND orm.raw_project_name = e.project_name
               AND orm.raw_building_name = e.building_name
               AND orm.property_type = e.property_type
            WHERE if(
                    lowerUTF8(e.market_status) = 'offplan'
                    AND orm.match_status IN ('auto_approved', 'manual_approved')
                    AND orm.normalized_reelly_project_name != '',
                    orm.normalized_reelly_project_name,
                    if(
                        lowerUTF8(e.market_status) = 'offplan' AND e.building_name != '',
                        e.building_name,
                        e.project_name
                    )
                  ) != ''
              AND e.transaction_date > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.transaction_date <= a.period_end
            GROUP BY project_key
        ),
        rents_by_project AS (
            SELECT
                replaceRegexpAll(lowerUTF8(trim(project_name)), '[^a-z0-9]', '') AS project_key,
                count() AS rental_contract_count,
                quantile(0.5)(annual_rent_aed) AS median_annual_rent,
                avgIf(
                    (annual_rent_aed / size_sqft) * {SQM_TO_SQFT},
                    annual_rent_aed > 0 AND size_sqft > 0
                ) AS avg_rent_price_sqm
            FROM dxbi_rental_events AS e FINAL
            CROSS JOIN activity_anchor AS a
            WHERE project_name != ''
              AND e.lease_start > a.period_end - toIntervalDay({{period_days:UInt16}})
              AND e.lease_start <= a.period_end
            GROUP BY project_key
        )
        SELECT
            -toInt64(g.property_id) AS project_id,
            coalesce(nullIf(f.project_name_en, ''), g.project_name_en) AS project_name_en,
            coalesce(nullIf(f.area_name_en, ''), g.area_name_en) AS area_name_en,
            coalesce(nullIf(f.developer_name, ''), g.developer_name) AS developer_name,
            f.master_project_en AS master_project_en,
            g.latitude AS latitude,
            g.longitude AS longitude,
            g.geo_pin_count AS geo_pin_count,
            g.coordinate_source AS coordinate_source,
            g.coordinate_method AS coordinate_method,
            g.detail_point_count AS detail_point_count,
            g.building_point_count AS building_point_count,
            g.land_point_count AS land_point_count,
            coalesce(
                nullIf(f.completion_status, ''),
                if(g.supply_readiness >= 100, 'Finished', '')
            ) AS completion_status,
            coalesce(
                nullIf(f.pipeline_status, ''),
                multiIf(
                    g.supply_completion_time BETWEEN today() AND today() + INTERVAL 365 DAY,
                        'delivering_next_12_months',
                    g.supply_completion_time > today(), 'pipeline',
                    ''
                )
            ) AS pipeline_status,
            coalesce(f.project_status, nullIf(g.supply_status, '')) AS project_status,
            ifNull(f.no_of_units, 0) AS no_of_units,
            ifNull(f.no_of_buildings, 0) AS no_of_buildings,
            coalesce(f.percent_completed, g.supply_readiness) AS percent_completed,
            ifNull(f.estimated_delivery_confidence, 0) AS estimated_delivery_confidence,
            g.entity_source AS entity_source,
            g.supply_status AS supply_status,
            g.supply_completion_time AS supply_completion_time,
            g.units_in_sale AS units_in_sale,
            ifNull(s.sales_transaction_count, 0) AS sales_transaction_count,
            ifNull(r.rental_contract_count, 0) AS rental_contract_count,
            ifNull(s.total_sales_volume, 0) AS total_sales_volume,
            nullIf(s.median_sale_price, 0) AS median_sale_price,
            nullIf(r.median_annual_rent, 0) AS median_annual_rent,
            if(
                s.sales_transaction_count >= {RADAR_YIELD_MIN_SAMPLE_COUNT}
                AND r.rental_contract_count >= {RADAR_YIELD_MIN_SAMPLE_COUNT}
                AND s.median_sale_price > 0
                AND r.median_annual_rent > 0,
                r.median_annual_rent / s.median_sale_price * 100,
                NULL
            ) AS gross_yield_pct,
            nullIf(s.avg_sale_price_sqm, 0) AS avg_sale_price_sqm,
            nullIf(r.avg_rent_price_sqm, 0) AS avg_rent_price_sqm,
            ifNull(s.sales_transaction_count, 0) AS yield_existing_sale_count,
            ifNull(r.rental_contract_count, 0) AS yield_rental_contract_count,
            nullIf(s.median_sale_price, 0) AS yield_existing_median_sale_price,
            nullIf(r.median_annual_rent, 0) AS yield_median_annual_rent
        FROM geo_by_project g
        LEFT JOIN fact_by_project f ON f.project_key = g.normalized_project_key
        LEFT JOIN sales_by_project s ON s.project_key = g.normalized_project_key
        LEFT JOIN rents_by_project r ON r.project_key = g.normalized_project_key
        WHERE {where_clause}
        ORDER BY
            (f.pipeline_status = 'delivering_next_12_months') DESC,
            f.no_of_units DESC,
            total_sales_volume DESC
        LIMIT {{limit:UInt32}}
    """


def _radar_project_pin_filters(
    *,
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
    area: str | None,
    developer: str | None,
) -> tuple[str, dict[str, Any]]:
    # The coordinate CTE already excludes unnamed projects. Keeping the base
    # predicate out of the outer query matters because ClickHouse otherwise
    # pushes it into the aggregation that produces the display name.
    filters = ["1"]
    params: dict[str, Any] = {}
    if west is not None and south is not None and east is not None and north is not None:
        filters.extend(
            [
                "g.longitude BETWEEN {west:Float64} AND {east:Float64}",
                "g.latitude BETWEEN {south:Float64} AND {north:Float64}",
            ]
        )
        params.update({"west": west, "south": south, "east": east, "north": north})
    if area:
        filters.append("lower(g.area_name_en) = lower({area:String})")
        params["area"] = area
    if developer:
        developer_names = developer_filter_names(developer)
        if developer_names:
            filters.append(
                """
                lower(coalesce(nullIf(f.developer_name, ''), g.developer_name))
                IN {developer_names:Array(String)}
                """
            )
            params["developer_names"] = developer_names
    return " AND ".join(filters), params


def _radar_building_pins_sql() -> str:
    return """
        WITH activity_anchor AS (
            SELECT greatest(
                (SELECT max(transaction_date)
                 FROM dxbi_sales_unit_events FINAL
                 WHERE transaction_date <= today()),
                (SELECT max(lease_start)
                 FROM dxbi_rental_events FINAL
                 WHERE lease_start <= today())
            ) AS period_end
        ),
        tower_nodes AS (
            SELECT
                canonical_location_id,
                source_location_id,
                name,
                latitude,
                longitude
            FROM geo_location_nodes
            WHERE location_type = 'TOWER'
              AND latitude BETWEEN {south:Float64} AND {north:Float64}
              AND longitude BETWEEN {west:Float64} AND {east:Float64}
              AND coordinate_status = 'valid'
        ),
        location_context AS (
            SELECT
                c.descendant_location_id AS canonical_location_id,
                argMinIf(n.name, c.depth, n.location_type = 'SUBCOMMUNITY')
                    AS project_name,
                argMinIf(n.name, c.depth, n.location_type = 'COMMUNITY')
                    AS area_name
            FROM geo_location_closure AS c
            INNER JOIN geo_location_nodes AS n
                ON n.canonical_location_id = c.ancestor_location_id
            INNER JOIN tower_nodes AS tower
                ON tower.canonical_location_id = c.descendant_location_id
            GROUP BY c.descendant_location_id
        ),
        tower_links AS (
            SELECT
                gm.source_system,
                gm.source_key,
                gm.canonical_location_id,
                gm.property_type,
                gm.market_status,
                gm.raw_area_name,
                gm.raw_project_name,
                gm.raw_building_name
            FROM geo_mapped_source_facts AS gm
            INNER JOIN tower_nodes AS tower
                ON tower.canonical_location_id = gm.canonical_location_id
            WHERE gm.source_system IN ('dxbi_sales', 'dxbi_rentals')
              AND gm.source_grain = 'building'
              AND gm.target_grain = 'tower'
              AND gm.match_status IN ('auto_approved', 'manual_approved')
        ),
        sales_by_tower AS (
            SELECT
                links.canonical_location_id,
                uniqExact(links.source_key) AS matched_sale_signatures,
                count() AS sales_transaction_count,
                sum(e.sale_amount_aed) AS total_sales_volume,
                quantile(0.5)(e.sale_amount_aed) AS median_sale_price,
                max(e.transaction_date) AS last_sale_date
            FROM dxbi_sales_unit_events AS e FINAL
            CROSS JOIN activity_anchor AS anchor
            INNER JOIN tower_links AS links
                ON links.source_system = 'dxbi_sales'
               AND links.raw_area_name = e.area_name
               AND links.raw_project_name = e.project_name
               AND links.raw_building_name = e.building_name
               AND links.property_type = e.property_type
               AND links.market_status = e.market_status
            WHERE lowerUTF8(e.market_status) != 'offplan'
              AND e.transaction_date > anchor.period_end
                    - toIntervalDay({period_days:UInt16})
              AND e.transaction_date <= anchor.period_end
            GROUP BY links.canonical_location_id
        ),
        rents_by_tower AS (
            SELECT
                links.canonical_location_id,
                uniqExact(links.source_key) AS matched_rental_signatures,
                count() AS rental_contract_count,
                quantile(0.5)(e.annual_rent_aed) AS median_annual_rent,
                max(e.lease_start) AS last_rental_date
            FROM dxbi_rental_events AS e FINAL
            CROSS JOIN activity_anchor AS anchor
            INNER JOIN tower_links AS links
                ON links.source_system = 'dxbi_rentals'
               AND links.raw_area_name = e.area_name
               AND links.raw_project_name = e.project_name
               AND links.raw_building_name = e.building_name
               AND links.property_type = e.property_type
               AND links.market_status = ''
            WHERE e.lease_start > anchor.period_end - toIntervalDay({period_days:UInt16})
              AND e.lease_start <= anchor.period_end
            GROUP BY links.canonical_location_id
        ),
        listings_by_tower AS (
            SELECT
                building_location_id AS source_location_id,
                uniqExactIf(
                    if(listing_id != '', listing_id, property_key),
                    is_available = 1
                ) AS listing_inventory_count
            FROM pf_listings_bronze
            INNER JOIN tower_nodes AS tower
                ON tower.source_location_id = building_location_id
            WHERE building_location_id != ''
            GROUP BY building_location_id
        )
        SELECT
            tower.canonical_location_id AS location_id,
            tower.source_location_id AS source_location_id,
            tower.name AS building_name,
            nullIf(context.project_name, '') AS project_name,
            if(context.area_name != '', context.area_name, 'Unknown') AS area_name,
            tower.latitude AS latitude,
            tower.longitude AS longitude,
            'property_finder' AS coordinate_source,
            'tower' AS coordinate_precision,
            ifNull(sales.matched_sale_signatures, 0)
                + ifNull(rents.matched_rental_signatures, 0) AS matched_source_signatures,
            ifNull(sales.sales_transaction_count, 0) AS sales_transaction_count,
            ifNull(rents.rental_contract_count, 0) AS rental_contract_count,
            ifNull(sales.total_sales_volume, 0) AS total_sales_volume,
            nullIf(sales.median_sale_price, 0) AS median_sale_price,
            nullIf(rents.median_annual_rent, 0) AS median_annual_rent,
            ifNull(listings.listing_inventory_count, 0) AS listing_inventory_count,
            nullIf(
                greatest(
                    ifNull(sales.last_sale_date, toDate(0)),
                    ifNull(rents.last_rental_date, toDate(0))
                ),
                toDate(0)
            ) AS last_activity_date
        FROM tower_nodes AS tower
        LEFT JOIN location_context AS context
            ON context.canonical_location_id = tower.canonical_location_id
        LEFT JOIN sales_by_tower AS sales
            ON sales.canonical_location_id = tower.canonical_location_id
        LEFT JOIN rents_by_tower AS rents
            ON rents.canonical_location_id = tower.canonical_location_id
        LEFT JOIN listings_by_tower AS listings
            ON listings.source_location_id = tower.source_location_id
        ORDER BY
            sales_transaction_count + rental_contract_count DESC,
            listing_inventory_count DESC,
            building_name
        LIMIT {limit:UInt32}
    """


def _radar_building_pins_from_rows(rows: list[dict[str, Any]]) -> list[RadarBuildingPin]:
    return [
        RadarBuildingPin(
            location_id=str(row["location_id"]),
            source_location_id=str(row["source_location_id"]),
            building_name=str(row["building_name"]),
            project_name=str(row.get("project_name") or "") or None,
            area_name=str(row.get("area_name") or "Unknown"),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            coordinate_source=str(row.get("coordinate_source") or "property_finder"),
            coordinate_precision=str(row.get("coordinate_precision") or "tower"),
            matched_source_signatures=int(row.get("matched_source_signatures") or 0),
            sales_transaction_count=int(row.get("sales_transaction_count") or 0),
            rental_contract_count=int(row.get("rental_contract_count") or 0),
            total_sales_volume=_float_or_none(row.get("total_sales_volume")) or 0.0,
            median_sale_price=_float_or_none(row.get("median_sale_price")),
            median_annual_rent=_float_or_none(row.get("median_annual_rent")),
            listing_inventory_count=int(row.get("listing_inventory_count") or 0),
            last_activity_date=row.get("last_activity_date"),
        )
        for row in rows
    ]


async def get_radar_building_pins(
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    limit: int = 3000,
    period_days: int = 365,
) -> list[RadarBuildingPin]:
    """Return physical PF tower pins for a bounded map viewport."""
    period_days = _validated_radar_period_days(period_days)
    rows = await query(
        _radar_building_pins_sql(),
        {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
            "limit": min(max(limit, 10), 10_000),
            "period_days": period_days,
        },
    )
    return _radar_building_pins_from_rows(rows)


async def get_project_radar_overview(period_days: int = 365) -> ProjectRadarOverviewResponse:
    """Return the initial radar payload without project pins."""
    period_days = _validated_radar_period_days(period_days)
    radar_geo_cte = _radar_geo_cte()
    params = {"period_days": period_days}
    area_rows, stats_rows, developer_rows = await asyncio.gather(
        query(_radar_area_sql(radar_geo_cte), params),
        query(_radar_stats_sql(radar_geo_cte), params),
        query(_radar_developer_lookup_sql(), {}),
    )
    developers = _developer_lookup(developer_rows)
    return ProjectRadarOverviewResponse(
        stats=_radar_stats_from_row(stats_rows[0] if stats_rows else {}, period_days),
        areas=_radar_areas_from_rows(area_rows, developers),
        source_notes=_radar_source_notes(period_days),
    )


async def get_project_radar_pins(
    *,
    limit: int = 700,
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    area: str | None = None,
    developer: str | None = None,
    period_days: int = 365,
) -> list[ProjectRadarProject]:
    """Return bounded project pins for a viewport, area, or developer overlay."""
    period_days = _validated_radar_period_days(period_days)
    radar_geo_cte = _radar_geo_cte()
    where_clause, params = _radar_project_pin_filters(
        west=west,
        south=south,
        east=east,
        north=north,
        area=area,
        developer=developer,
    )
    params["limit"] = limit
    params["period_days"] = period_days
    project_rows, developer_rows = await asyncio.gather(
        query(_radar_project_pins_sql(radar_geo_cte, where_clause), params),
        query(_radar_developer_lookup_sql(), {}),
    )
    return _radar_projects_from_rows(project_rows, _developer_lookup(developer_rows))


async def get_project_radar(limit: int = 1400, period_days: int = 365) -> ProjectRadarResponse:
    """Return the legacy combined radar payload from the fast serving paths."""
    period_days = _validated_radar_period_days(period_days)
    overview, projects = await asyncio.gather(
        get_project_radar_overview(period_days=period_days),
        get_project_radar_pins(
            limit=min(max(limit, 10), 1400),
            period_days=period_days,
        ),
    )
    return ProjectRadarResponse(
        stats=overview.stats,
        areas=overview.areas,
        projects=projects,
        source_notes=overview.source_notes,
    )

    # Kept below temporarily as reference for the richer raw query while the
    # serving endpoint uses materialized facts and DXBI coordinates above.
    radar_geo_cte = _radar_geo_cte()

    project_sql = f"""
        WITH {radar_geo_cte},
        project_existing_sales AS (
            SELECT
                project_name_en,
                count() AS yield_existing_sale_count,
                median(actual_worth) AS yield_existing_median_sale_price
            FROM ch_transactions
            WHERE trans_group_en = 'Sales'
              AND property_type_en = 'Unit'
              AND property_usage_en = 'Residential'
              AND reg_type_en = 'Existing Properties'
              AND actual_worth > 0
              AND project_name_en != ''
            GROUP BY project_name_en
        ),
        project_rents AS (
            SELECT
                project_name_en,
                count() AS yield_rental_contract_count,
                median(annual_amount) AS yield_median_annual_rent
            FROM ch_rent_contracts
            WHERE property_usage_en = 'Residential'
              AND ejari_property_type_en = 'Flat'
              AND annual_amount > 0
              AND project_name_en != ''
            GROUP BY project_name_en
        )
        SELECT
            f.project_id AS project_id,
            f.project_name_en AS project_name_en,
            f.area_name_en AS area_name_en,
            coalesce(
                nullIf(dm.developer_name_en, ''),
                nullIf(p.master_developer_name, ''),
                nullIf(d.developer_name_en, ''),
                nullIf(da.developer_name_en, ''),
                nullIf(p.developer_name, ''),
                nullIf(f.developer_name, '')
            ) AS developer_name,
            f.master_project_en AS master_project_en,
            g.latitude AS latitude,
            g.longitude AS longitude,
            g.geo_pin_count AS geo_pin_count,
            g.coordinate_source AS coordinate_source,
            g.coordinate_method AS coordinate_method,
            g.detail_point_count AS detail_point_count,
            g.building_point_count AS building_point_count,
            g.land_point_count AS land_point_count,
            f.completion_status AS completion_status,
            f.pipeline_status AS pipeline_status,
            p.project_status AS project_status,
            f.no_of_units AS no_of_units,
            p.no_of_buildings AS no_of_buildings,
            f.percent_completed AS percent_completed,
            f.estimated_delivery_confidence AS estimated_delivery_confidence,
            f.sales_transaction_count_12m AS sales_transaction_count_12m,
            f.rental_contract_count_12m AS rental_contract_count_12m,
            f.total_sales_volume_12m AS total_sales_volume_12m,
            coalesce(pes.yield_existing_median_sale_price, f.median_sale_price) AS median_sale_price,
            coalesce(pr.yield_median_annual_rent, f.median_annual_rent) AS median_annual_rent,
            pes.yield_existing_sale_count AS yield_existing_sale_count,
            pes.yield_existing_median_sale_price AS yield_existing_median_sale_price,
            pr.yield_rental_contract_count AS yield_rental_contract_count,
            pr.yield_median_annual_rent AS yield_median_annual_rent,
            f.avg_sale_price_sqm_12m AS avg_sale_price_sqm_12m,
            f.avg_rent_price_sqm_12m AS avg_rent_price_sqm_12m
        FROM ch_project_fact f
        INNER JOIN ch_projects p ON p.project_id = f.project_id
        INNER JOIN geo_by_project g ON g.project_id = f.project_id
        LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
        LEFT JOIN ch_developers dm ON p.master_developer_id = dm.developer_id
        LEFT JOIN ch_developers da ON f.developer_name = da.developer_name_ar
        LEFT JOIN project_existing_sales pes ON lower(pes.project_name_en) = lower(f.project_name_en)
        LEFT JOIN project_rents pr ON lower(pr.project_name_en) = lower(f.project_name_en)
        WHERE f.project_name_en != ''
        ORDER BY
            (f.pipeline_status = 'delivering_next_12_months') DESC,
            f.no_of_units DESC,
            f.total_sales_volume_12m DESC
        LIMIT {{limit:UInt32}}
    """

    area_sql = f"""
        WITH {radar_geo_cte},
        area_geo AS (
            SELECT
                p.area_name_en,
                avg(g.latitude) AS latitude,
                avg(g.longitude) AS longitude,
                countDistinct(p.project_id) AS mapped_projects
            FROM ch_projects p
            INNER JOIN geo_by_project g ON g.project_id = p.project_id
            WHERE p.area_name_en != ''
            GROUP BY p.area_name_en
        ),
        dda_summary AS (
            SELECT
                community_name,
                count() AS dda_plot_count,
                sum(plot_area_sqm) AS dda_total_plot_area_sqm,
                sum(max_gfa_sqm) AS dda_total_gfa_sqm,
                arrayFilter(x -> x != '', topK(5)(land_use)) AS dda_dominant_land_uses
            FROM ch_gis_land_plots FINAL
            WHERE coordinates != ''
              AND community_name != ''
            GROUP BY community_name
        ),
        area_existing_sales AS (
            SELECT
                area_name_en,
                count() AS yield_existing_sale_count,
                median(actual_worth) AS yield_existing_median_sale_price
            FROM ch_transactions
            WHERE trans_group_en = 'Sales'
              AND property_type_en = 'Unit'
              AND property_usage_en = 'Residential'
              AND reg_type_en = 'Existing Properties'
              AND actual_worth > 0
              AND area_name_en != ''
            GROUP BY area_name_en
        ),
        area_rents AS (
            SELECT
                area_name_en,
                count() AS yield_rental_contract_count,
                median(annual_amount) AS yield_median_annual_rent
            FROM ch_rent_contracts
            WHERE property_usage_en = 'Residential'
              AND ejari_property_type_en = 'Flat'
              AND annual_amount > 0
              AND area_name_en != ''
            GROUP BY area_name_en
        )
        SELECT
            af.area_id AS area_id,
            af.area_name_en AS area_name_en,
            ag.latitude AS latitude,
            ag.longitude AS longitude,
            ifNull(ag.mapped_projects, 0) AS mapped_projects,
            af.active_projects AS active_projects,
            af.completed_projects AS completed_projects,
            af.overdue_projects AS overdue_projects,
            af.pipeline_units AS pipeline_units,
            af.units_delivering_next_12_months AS units_delivering_next_12_months,
            af.active_developers AS active_developers,
            af.avg_completion_pct AS avg_completion_pct,
            af.avg_delivery_confidence AS avg_delivery_confidence,
            af.sales_transaction_count_12m AS sales_transaction_count_12m,
            af.rental_contract_count_12m AS rental_contract_count_12m,
            af.total_sales_volume_12m AS total_sales_volume_12m,
            coalesce(aes.yield_existing_median_sale_price, af.median_sale_price) AS median_sale_price,
            coalesce(ar.yield_median_annual_rent, af.median_annual_rent) AS median_annual_rent,
            aes.yield_existing_sale_count AS yield_existing_sale_count,
            aes.yield_existing_median_sale_price AS yield_existing_median_sale_price,
            ar.yield_rental_contract_count AS yield_rental_contract_count,
            ar.yield_median_annual_rent AS yield_median_annual_rent,
            af.avg_sale_price_sqm_12m AS avg_sale_price_sqm_12m,
            af.avg_rent_price_sqm_12m AS avg_rent_price_sqm_12m,
            af.top_developers AS top_developers,
            af.top_master_projects AS top_master_projects,
            ifNull(ds.dda_plot_count, 0) AS dda_plot_count,
            ifNull(ds.dda_total_plot_area_sqm, 0) AS dda_total_plot_area_sqm,
            ifNull(ds.dda_total_gfa_sqm, 0) AS dda_total_gfa_sqm,
            ifNull(ds.dda_dominant_land_uses, []) AS dda_dominant_land_uses
        FROM ch_area_fact af
        LEFT JOIN area_geo ag ON lower(ag.area_name_en) = lower(af.area_name_en)
        LEFT JOIN dda_summary ds ON lower(ds.community_name) = lower(af.area_name_en)
        LEFT JOIN area_existing_sales aes ON lower(aes.area_name_en) = lower(af.area_name_en)
        LEFT JOIN area_rents ar ON lower(ar.area_name_en) = lower(af.area_name_en)
        WHERE af.area_name_en != ''
          AND lower(af.area_name_en) != 'unknown'
        ORDER BY af.pipeline_units DESC, af.sales_transaction_count_12m DESC
        LIMIT 90
    """

    area_sql = _radar_area_sql(radar_geo_cte)

    developer_lookup_sql = """
        SELECT developer_name_ar, developer_name_en
        FROM ch_developers
        WHERE developer_name_en != ''
    """

    stats_sql = f"""
        WITH {radar_geo_cte}
        SELECT
            count() AS total_projects,
            (SELECT countDistinct(project_id) FROM geo_by_project) AS mapped_projects,
            countIf(completion_status != 'FINISHED') AS active_projects,
            countIf(completion_status = 'FINISHED') AS finished_projects,
            sumIf(no_of_units, completion_status != 'FINISHED') AS pipeline_units,
            sumIf(
                no_of_units,
                pipeline_status = 'delivering_next_12_months' AND completion_status != 'FINISHED'
            )
                AS units_delivering_next_12_months,
            sum(sales_transaction_count_12m) AS sales_transaction_count_12m,
            sum(rental_contract_count_12m) AS rental_contract_count_12m,
            sum(total_sales_volume_12m) AS total_sales_volume_12m,
            (
                SELECT count()
                FROM ch_gis_land_plots FINAL
                WHERE coordinates != ''
            ) AS dda_plot_count,
            (
                SELECT sum(plot_area_sqm)
                FROM ch_gis_land_plots FINAL
                WHERE coordinates != ''
            ) AS dda_total_plot_area_sqm,
            (
                SELECT sum(max_gfa_sqm)
                FROM ch_gis_land_plots FINAL
                WHERE coordinates != ''
            ) AS dda_total_gfa_sqm
        FROM ch_project_fact
    """

    project_rows, area_rows, stats_rows, developer_rows = await asyncio.gather(
        query(project_sql, {"limit": limit}),
        query(area_sql, {}),
        query(stats_sql, {}),
        query(developer_lookup_sql, {}),
    )
    developers = _developer_lookup(developer_rows)

    projects = [
        ProjectRadarProject(
            project_id=row["project_id"],
            project_name=row["project_name_en"],
            area_name=row.get("area_name_en") or "Unknown",
            developer_name=_developer_display_name(row.get("developer_name"), developers),
            master_project_en=row.get("master_project_en") or None,
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            geo_pin_count=int(row.get("geo_pin_count") or 0),
            coordinate_source=row.get("coordinate_source") or CH_GEO_BUILDINGS_SOURCE,
            coordinate_method=row.get("coordinate_method") or None,
            detail_point_count=int(row.get("detail_point_count") or 0),
            building_point_count=int(row.get("building_point_count") or 0),
            land_point_count=int(row.get("land_point_count") or 0),
            completion_status=row.get("completion_status") or "",
            pipeline_status=row.get("pipeline_status") or "",
            project_status=row.get("project_status") or None,
            no_of_units=int(row.get("no_of_units") or 0),
            no_of_buildings=int(row.get("no_of_buildings") or 0),
            percent_completed=_float_or_none(row.get("percent_completed")),
            delivery_confidence=_float_or_none(row.get("estimated_delivery_confidence")) or 0.0,
            sales_transaction_count_12m=int(row.get("sales_transaction_count_12m") or 0),
            rental_contract_count_12m=int(row.get("rental_contract_count_12m") or 0),
            total_sales_volume_12m=_float_or_none(row.get("total_sales_volume_12m")) or 0.0,
            median_sale_price=_float_or_none(row.get("median_sale_price")),
            median_annual_rent=_float_or_none(row.get("median_annual_rent")),
            gross_yield_pct=_radar_gross_yield_pct(row),
            avg_sale_price_sqm_12m=_float_or_none(row.get("avg_sale_price_sqm_12m")),
            avg_rent_price_sqm_12m=_float_or_none(row.get("avg_rent_price_sqm_12m")),
        )
        for row in project_rows
    ]

    areas = [
        ProjectRadarArea(
            area_id=int(row.get("area_id") or 0),
            area_name=row.get("area_name_en") or "Unknown",
            latitude=_float_or_none(row.get("latitude")),
            longitude=_float_or_none(row.get("longitude")),
            mapped_projects=int(row.get("mapped_projects") or 0),
            active_projects=int(row.get("active_projects") or 0),
            completed_projects=int(row.get("completed_projects") or 0),
            overdue_projects=int(row.get("overdue_projects") or 0),
            pipeline_units=int(row.get("pipeline_units") or 0),
            units_delivering_next_12_months=int(row.get("units_delivering_next_12_months") or 0),
            active_developers=int(row.get("active_developers") or 0),
            avg_completion_pct=_float_or_none(row.get("avg_completion_pct")) or 0.0,
            avg_delivery_confidence=_float_or_none(row.get("avg_delivery_confidence")) or 0.0,
            sales_transaction_count_12m=int(row.get("sales_transaction_count_12m") or 0),
            rental_contract_count_12m=int(row.get("rental_contract_count_12m") or 0),
            total_sales_volume_12m=_float_or_none(row.get("total_sales_volume_12m")) or 0.0,
            median_sale_price=_float_or_none(row.get("median_sale_price")),
            median_annual_rent=_float_or_none(row.get("median_annual_rent")),
            avg_sale_price_sqm_12m=_float_or_none(row.get("avg_sale_price_sqm_12m")),
            avg_rent_price_sqm_12m=_float_or_none(row.get("avg_rent_price_sqm_12m")),
            gross_yield_pct=_radar_gross_yield_pct(row),
            top_developers=_developer_display_list(row.get("top_developers"), developers, limit=5),
            top_master_projects=list(row.get("top_master_projects") or [])[:5],
            dda_plot_count=int(row.get("dda_plot_count") or 0),
            dda_total_plot_area_sqm=_float_or_none(row.get("dda_total_plot_area_sqm")) or 0.0,
            dda_total_gfa_sqm=_float_or_none(row.get("dda_total_gfa_sqm")) or 0.0,
            dda_dominant_land_uses=_land_use_labels(row.get("dda_dominant_land_uses"), limit=5),
        )
        for row in area_rows
    ]
    unique_areas: list[ProjectRadarArea] = []
    seen_area_names: set[str] = set()
    for area in areas:
        area_key = area.area_name.strip().lower()
        if area_key in seen_area_names:
            continue
        seen_area_names.add(area_key)
        unique_areas.append(area)
    areas = unique_areas

    stats_row = stats_rows[0] if stats_rows else {}
    stats = ProjectRadarStats(
        total_projects=int(stats_row.get("total_projects") or 0),
        mapped_projects=int(stats_row.get("mapped_projects") or 0),
        active_projects=int(stats_row.get("active_projects") or 0),
        finished_projects=int(stats_row.get("finished_projects") or 0),
        pipeline_units=int(stats_row.get("pipeline_units") or 0),
        units_delivering_next_12_months=int(stats_row.get("units_delivering_next_12_months") or 0),
        sales_transaction_count_12m=int(stats_row.get("sales_transaction_count_12m") or 0),
        rental_contract_count_12m=int(stats_row.get("rental_contract_count_12m") or 0),
        total_sales_volume_12m=_float_or_none(stats_row.get("total_sales_volume_12m")) or 0.0,
        dda_plot_count=int(stats_row.get("dda_plot_count") or 0),
        dda_total_plot_area_sqm=_float_or_none(stats_row.get("dda_total_plot_area_sqm")) or 0.0,
        dda_total_gfa_sqm=_float_or_none(stats_row.get("dda_total_gfa_sqm")) or 0.0,
    )

    return ProjectRadarResponse(
        stats=stats,
        projects=projects,
        areas=areas,
        source_notes=_radar_source_notes(365),
    )


async def get_building_details(property_id: int) -> Optional[BuildingDetailResponse]:
    """Get building metadata and unit composition by bedroom type."""
    building_sql = """
        SELECT
            property_id,
            building_number,
            floors,
            project_id,
            project_name_en,
            area_name_en
        FROM ch_buildings
        WHERE property_id = {property_id:Int32}
        LIMIT 1
    """
    building_result = await query(building_sql, {"property_id": property_id})
    if not building_result:
        return None

    b = building_result[0]

    units_sql = """
        SELECT
            rooms_en,
            count() AS count,
            round(avg(actual_area), 2) AS avg_area_sqm
        FROM ch_units
        WHERE parent_property_id = {property_id:Int32}
          AND rooms_en != ''
        GROUP BY rooms_en
        ORDER BY count DESC
    """
    units_result = await query(units_sql, {"property_id": property_id})

    total_units = sum(row["count"] for row in units_result)
    unit_composition = [
        BuildingUnitType(
            rooms_en=row["rooms_en"],
            count=row["count"],
            percentage=round((row["count"] / total_units) * 100, 1) if total_units else 0,
            avg_area_sqm=float(row["avg_area_sqm"]) if row["avg_area_sqm"] else None,
        )
        for row in units_result
    ]
    unit_composition.sort(key=lambda row: _room_sort_key(row.rooms_en))

    return BuildingDetailResponse(
        property_id=b["property_id"],
        building_number=b.get("building_number") or None,
        floors=b.get("floors") or None,
        project_id=b["project_id"],
        project_name=b.get("project_name_en") or f"Project {b['project_id']}",
        area_name=b.get("area_name_en") or "Unknown",
        total_units=total_units,
        unit_composition=unit_composition,
    )


def _dubai_local_tm_to_lng_lat(easting: float, northing: float) -> list[float]:
    """Convert Dubai Local Transverse Mercator coordinates to WGS84 lng/lat."""
    semi_major_axis = 6378137.0
    flattening = 1 / 298.257223563
    scale_factor = 1.0
    eccentricity_sq = flattening * (2 - flattening)
    second_eccentricity_sq = eccentricity_sq / (1 - eccentricity_sq)

    x = easting - 500000.0
    y = northing
    central_meridian = math.radians(55.3333333333333)

    meridional_arc = y / scale_factor
    mu = meridional_arc / (
        semi_major_axis
        * (1 - eccentricity_sq / 4 - 3 * eccentricity_sq**2 / 64 - 5 * eccentricity_sq**3 / 256)
    )

    e1 = (1 - math.sqrt(1 - eccentricity_sq)) / (1 + math.sqrt(1 - eccentricity_sq))
    footprint_lat = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    sin_fp = math.sin(footprint_lat)
    cos_fp = math.cos(footprint_lat)
    tan_fp = math.tan(footprint_lat)

    c1 = second_eccentricity_sq * cos_fp**2
    t1 = tan_fp**2
    n1 = semi_major_axis / math.sqrt(1 - eccentricity_sq * sin_fp**2)
    r1 = semi_major_axis * (1 - eccentricity_sq) / (1 - eccentricity_sq * sin_fp**2) ** 1.5
    d = x / (n1 * scale_factor)

    lat = footprint_lat - (n1 * tan_fp / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * second_eccentricity_sq) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * second_eccentricity_sq - 3 * c1**2)
        * d**6
        / 720
    )
    lon = (
        central_meridian
        + (
            d
            - (1 + 2 * t1 + c1) * d**3 / 6
            + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * second_eccentricity_sq + 24 * t1**2)
            * d**5
            / 120
        )
        / cos_fp
    )

    return [math.degrees(lon), math.degrees(lat)]


def _normalize_plot_coordinate(pair: Any) -> list[float] | None:
    if not isinstance(pair, list) or len(pair) != 2:
        return None
    try:
        x = float(pair[0])
        y = float(pair[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None

    if -180 <= x <= 180 and -90 <= y <= 90:
        return [x, y]
    if 100000 <= x <= 900000 and 0 <= y <= 10000000:
        return _dubai_local_tm_to_lng_lat(x, y)
    return None


def _parse_plot_coordinates(raw: str) -> list[list[float]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        coords = [
            coordinate for p in parsed if (coordinate := _normalize_plot_coordinate(p)) is not None
        ]
        if len(coords) >= 3 and coords[0] != coords[-1]:
            coords.append(coords[0])
        return coords
    except Exception:
        return []


def _coordinate_bounds(coordinates: list[list[float]]) -> tuple[float, float, float, float]:
    lngs = [point[0] for point in coordinates]
    lats = [point[1] for point in coordinates]
    return min(lngs), min(lats), max(lngs), max(lats)


def _bounds_intersects(
    plot_bounds: tuple[float, float, float, float],
    *,
    west: float,
    south: float,
    east: float,
    north: float,
) -> bool:
    plot_west, plot_south, plot_east, plot_north = plot_bounds
    return plot_west <= east and plot_east >= west and plot_south <= north and plot_north >= south


def _dda_land_use_text(row: dict[str, Any]) -> str:
    labels = row.get("land_use_summary") or []
    return " ".join(str(label) for label in labels).lower()


def _is_small_villa_plot(row: dict[str, Any]) -> bool:
    land_use = _dda_land_use_text(row)
    return (
        0 < (_float_or_none(row.get("plot_area_sqm")) or 0) <= DDA_VILLA_MAX_PLOT_AREA_SQM
        and "residential" in land_use
        and any(token in land_use for token in ("villa", "townhouse", "attached"))
    )


def _is_non_developable_plot(row: dict[str, Any]) -> bool:
    land_use = _dda_land_use_text(row)
    buildable = any(
        token in land_use
        for token in ("residential", "commercial", "office", "retail", "hotel", "hospitality")
    )
    non_developable = any(
        token in land_use
        for token in (
            "open space",
            "landscape",
            "park",
            "utilities",
            "substation",
            "feeder pillar",
            "utility corridor",
            "transport",
            "access road",
            "sikka",
        )
    )
    return non_developable and not buildable


def _dda_subdivision_key(row: dict[str, Any]) -> str:
    project_name = str(row.get("project_name") or "").strip().lower()
    community_name = str(row.get("community_name") or "").strip().lower()
    return f"project:{project_name}" if project_name else f"community:{community_name}"


def _annotate_dda_development_evidence(rows: list[dict[str, Any]]) -> None:
    """Attach conservative development evidence, including villa-subdivision inference.

    DLD building parcel ids directly verify many DDA plots. Small villa plots are
    frequently individual cadastral parcels with no point coordinate of their own,
    so a separate probable state is used when confirmed siblings show that the
    enclosing carved-out subdivision is developed.
    """
    subdivision_stats: dict[str, dict[str, int]] = {}
    for row in rows:
        if not _is_small_villa_plot(row):
            continue
        stats = subdivision_stats.setdefault(
            _dda_subdivision_key(row),
            {"plot_count": 0, "confirmed_count": 0},
        )
        stats["plot_count"] += 1
        if _int_value(row.get("linked_physical_asset_count")) > 0:
            stats["confirmed_count"] += 1

    today_date = date.today()
    for row in rows:
        linked_assets = _int_value(row.get("linked_asset_count"))
        physical_assets = _int_value(row.get("linked_physical_asset_count"))
        subdivision = subdivision_stats.get(_dda_subdivision_key(row), {})
        subdivision_plot_count = int(subdivision.get("plot_count") or 0)
        subdivision_confirmed_count = int(subdivision.get("confirmed_count") or 0)
        row["subdivision_plot_count"] = subdivision_plot_count
        row["subdivision_confirmed_count"] = subdivision_confirmed_count

        if _is_non_developable_plot(row):
            row.update(
                development_status="non_developable",
                development_confidence="high",
                development_method="planning_land_use",
                development_note="Planning use is infrastructure, utility, transport, or open space.",
            )
        elif physical_assets > 0:
            row.update(
                development_status="developed_confirmed",
                development_confidence="high",
                development_method="parcel_id_exact",
                development_note=f"{physical_assets:,} physical DLD asset record(s) match this parcel.",
            )
        elif linked_assets > 0:
            row.update(
                development_status="developed_probable",
                development_confidence="medium",
                development_method="parcel_id_asset_record",
                development_note=f"{linked_assets:,} DLD asset record(s) match this parcel without complete physical fields.",
            )
        elif (
            _is_small_villa_plot(row)
            and subdivision_plot_count >= DDA_VILLA_SUBDIVISION_MIN_PLOTS
            and subdivision_confirmed_count > 0
        ):
            row.update(
                development_status="developed_probable",
                development_confidence="medium",
                development_method="villa_subdivision_inference",
                development_note=(
                    "Individual villa parcel inferred from its carved-out subdivision: "
                    f"{subdivision_confirmed_count:,} of {subdivision_plot_count:,} sibling plots "
                    "have confirmed development evidence."
                ),
            )
        else:
            site_plan_issue_date = row.get("site_plan_issue_date")
            site_plan_expiry_date = row.get("site_plan_expiry_date")
            active_site_plan = bool(
                site_plan_issue_date
                and (site_plan_expiry_date is None or site_plan_expiry_date >= today_date)
            )
            if active_site_plan:
                row.update(
                    development_status="planned_unbuilt_candidate",
                    development_confidence="low",
                    development_method="active_site_plan_without_asset",
                    development_note="An active site plan exists, but no developed asset is currently linked.",
                )
            else:
                row.update(
                    development_status="no_observed_asset",
                    development_confidence="low",
                    development_method="no_observed_asset",
                    development_note="No direct or subdivision-level developed asset evidence was observed.",
                )


async def _get_dda_plot_geometries() -> list[dict[str, Any]]:
    global _dda_geometry_cache

    now = time.monotonic()
    if _dda_geometry_cache and now - _dda_geometry_cache[0] < DDA_GEOMETRY_CACHE_TTL_SECONDS:
        return _dda_geometry_cache[1]

    sql = """
    WITH parcel_assets AS (
        SELECT
            parcel_id,
            count() AS linked_asset_count,
            countIf(floors > 0 OR units > 0 OR built_up_area > 0 OR actual_area > 0)
                AS linked_physical_asset_count
        FROM ch_buildings
        WHERE parcel_id != ''
        GROUP BY parcel_id
    )
    SELECT
        p.plot_number,
        p.project_name,
        p.community_name,
        p.plot_area_sqm,
        p.max_gfa_sqm,
        p.max_height,
        p.max_coverage,
        p.site_plan_issue_date,
        p.site_plan_expiry_date,
        p.land_use,
        p.gfa_type,
        p.is_verified,
        p.coordinates,
        ifNull(a.linked_asset_count, 0) AS linked_asset_count,
        ifNull(a.linked_physical_asset_count, 0) AS linked_physical_asset_count
    FROM ch_gis_land_plots AS p FINAL
    LEFT JOIN parcel_assets AS a ON a.parcel_id = p.plot_number
    WHERE p.coordinates != ''
    LIMIT 100000
    """
    rows = await query(sql, {})
    geometries: list[dict[str, Any]] = []
    for row in rows:
        coordinates = _parse_plot_coordinates(row.get("coordinates", ""))
        if len(coordinates) < 3:
            continue
        geometries.append(
            {
                "plot_number": row.get("plot_number") or "",
                "project_name": row.get("project_name") or "",
                "community_name": row.get("community_name") or "",
                "plot_area_sqm": _float_or_none(row.get("plot_area_sqm")) or 0.0,
                "max_gfa_sqm": _float_or_none(row.get("max_gfa_sqm")),
                "max_height": row.get("max_height") or None,
                "max_coverage": row.get("max_coverage") or None,
                "site_plan_issue_date": row.get("site_plan_issue_date"),
                "site_plan_expiry_date": row.get("site_plan_expiry_date"),
                "land_use": row.get("land_use") or None,
                "gfa_type": row.get("gfa_type") or None,
                "is_verified": bool(row.get("is_verified") or False),
                "coordinates": coordinates,
                "bounds": _coordinate_bounds(coordinates),
                "land_use_summary": _land_use_labels(row.get("land_use"), limit=4),
                "linked_asset_count": int(row.get("linked_asset_count") or 0),
                "linked_physical_asset_count": int(row.get("linked_physical_asset_count") or 0),
            }
        )

    _annotate_dda_development_evidence(geometries)
    _dda_geometry_cache = (now, geometries)
    return geometries


def _convex_hull(points: list[list[float]]) -> list[list[float]]:
    unique_points = sorted({(round(point[0], 8), round(point[1], 8)) for point in points})
    if len(unique_points) < 3:
        return []

    def cross(
        origin: tuple[float, float],
        point_a: tuple[float, float],
        point_b: tuple[float, float],
    ) -> float:
        return (point_a[0] - origin[0]) * (point_b[1] - origin[1]) - (point_a[1] - origin[1]) * (
            point_b[0] - origin[0]
        )

    lower: list[tuple[float, float]] = []
    for point in unique_points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = [[lng, lat] for lng, lat in lower[:-1] + upper[:-1]]
    if len(hull) >= 3:
        hull.append(hull[0])
    return hull


async def get_dda_outlines_for_bounds(
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    zoom: float,
    limit: int = 160,
) -> list[DDAOutlineFeature]:
    """Return coarse DDA outlines for low-zoom planning context."""
    rows = await _get_dda_plot_geometries()
    group_by_project = zoom >= 12
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        coords = row["coordinates"]
        if not _bounds_intersects(
            row["bounds"],
            west=west,
            south=south,
            east=east,
            north=north,
        ):
            continue

        project_name = str(row.get("project_name") or "").strip()
        community_name = str(row.get("community_name") or "").strip()
        name = project_name if group_by_project and project_name else community_name
        if not name:
            continue

        group = groups.setdefault(
            name,
            {
                "name": name,
                "kind": "project" if group_by_project and project_name else "community",
                "points": [],
                "plot_count": 0,
                "total_plot_area_sqm": 0.0,
                "total_gfa_sqm": 0.0,
                "land_uses": [],
                "development_counts": {},
            },
        )
        group["points"].extend(coords[:-1] if coords[0] == coords[-1] else coords)
        group["plot_count"] += 1
        group["total_plot_area_sqm"] += row["plot_area_sqm"]
        group["total_gfa_sqm"] += row["max_gfa_sqm"] or 0.0
        group["land_uses"].extend(row["land_use_summary"][:2])
        development_status = str(row.get("development_status") or "no_observed_asset")
        group["development_counts"][development_status] = (
            group["development_counts"].get(development_status, 0) + 1
        )

    min_plot_count = 8 if zoom < 12 else 3
    outlines: list[DDAOutlineFeature] = []
    for group in sorted(
        groups.values(),
        key=lambda item: (item["plot_count"], item["total_plot_area_sqm"]),
        reverse=True,
    ):
        if group["plot_count"] < min_plot_count:
            continue
        hull = _convex_hull(group["points"])
        if len(hull) < 4:
            continue
        land_uses = list(dict.fromkeys(group["land_uses"]))[:4]
        development_counts = group["development_counts"]
        developed_count = int(development_counts.get("developed_confirmed", 0)) + int(
            development_counts.get("developed_probable", 0)
        )
        outlines.append(
            DDAOutlineFeature(
                name=group["name"],
                kind=group["kind"],
                plot_count=group["plot_count"],
                total_plot_area_sqm=round(group["total_plot_area_sqm"], 2),
                total_gfa_sqm=round(group["total_gfa_sqm"], 2),
                coordinates=hull,
                land_use_summary=land_uses,
                developed_confirmed_count=int(development_counts.get("developed_confirmed", 0)),
                developed_probable_count=int(development_counts.get("developed_probable", 0)),
                planned_unbuilt_count=int(development_counts.get("planned_unbuilt_candidate", 0)),
                no_observed_asset_count=int(development_counts.get("no_observed_asset", 0)),
                non_developable_count=int(development_counts.get("non_developable", 0)),
                developed_share=round(developed_count / max(1, group["plot_count"]) * 100, 1),
            )
        )
        if len(outlines) >= limit:
            break
    return outlines


async def get_project_market_snapshot(project_id: int) -> Optional[ProjectMarketSnapshotResponse]:
    result = await query(
        """
        SELECT
            project_id,
            project_name_en,
            area_name_en,
            developer_name,
            master_project_en,
            completion_status,
            pipeline_status,
            estimated_delivery_confidence,
            sales_transaction_count_12m,
            rental_contract_count_12m,
            total_sales_volume_12m,
            median_sale_price,
            median_annual_rent,
            gross_yield_pct,
            avg_sale_price_sqm_12m,
            avg_rent_price_sqm_12m
        FROM ch_project_fact
        WHERE project_id = {project_id:Int32}
        LIMIT 1
        """,
        {"project_id": project_id},
    )
    if not result:
        return None
    row = result[0]
    return ProjectMarketSnapshotResponse(
        project_id=row["project_id"],
        project_name=row.get("project_name_en") or f"Project {row['project_id']}",
        area_name=row.get("area_name_en") or "Unknown",
        developer_name=row.get("developer_name") or None,
        master_project_en=row.get("master_project_en") or None,
        completion_status=row.get("completion_status") or "planned",
        pipeline_status=row.get("pipeline_status") or "unscheduled",
        estimated_delivery_confidence=float(row.get("estimated_delivery_confidence") or 0),
        sales_transaction_count_12m=row.get("sales_transaction_count_12m", 0),
        rental_contract_count_12m=row.get("rental_contract_count_12m", 0),
        total_sales_volume_12m=float(row.get("total_sales_volume_12m") or 0),
        median_sale_price=row.get("median_sale_price"),
        median_annual_rent=row.get("median_annual_rent"),
        gross_yield_pct=row.get("gross_yield_pct"),
        avg_sale_price_sqm_12m=row.get("avg_sale_price_sqm_12m"),
        avg_rent_price_sqm_12m=row.get("avg_rent_price_sqm_12m"),
    )


def _empty_dda_valuation(note: str) -> dict[str, Any]:
    return {
        "valuation_rate_min_aed_sqft": None,
        "valuation_rate_max_aed_sqft": None,
        "valuation_min_aed": None,
        "valuation_max_aed": None,
        "valuation_confidence": None,
        "valuation_note": note,
    }


def _community_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _plot_far(row: dict[str, Any]) -> float | None:
    plot_area_sqm = _float_or_none(row.get("plot_area_sqm"))
    max_gfa_sqm = _float_or_none(row.get("max_gfa_sqm"))
    if not plot_area_sqm or plot_area_sqm <= 0 or not max_gfa_sqm or max_gfa_sqm <= 0:
        return None
    return max_gfa_sqm / plot_area_sqm


def _far_band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 1.5:
        return "low"
    if value < 3.0:
        return "mid"
    return "development"


def _percentile(values: list[float], percentile: float) -> float | None:
    valid = sorted(value for value in values if math.isfinite(value))
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]
    position = (len(valid) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(valid) - 1)
    weight = position - lower_index
    return valid[lower_index] * (1 - weight) + valid[upper_index] * weight


def _valuation_rate_range(rates: list[float]) -> tuple[float, float] | None:
    valid = sorted(rate for rate in rates if rate > 0 and math.isfinite(rate))
    if not valid:
        return None
    if len(valid) == 1:
        rate = valid[0]
        return rate * 0.9, rate * 1.1
    if len(valid) < 4:
        return valid[0], valid[-1]
    low = _percentile(valid, 0.25)
    high = _percentile(valid, 0.75)
    if low is None or high is None:
        return None
    if low == high:
        return low * 0.95, high * 1.05
    return low, high


def _evidence_size_match(evidence: dict[str, Any], plot_area_sqm: float) -> bool:
    matched_area = _float_or_none(evidence.get("matched_plot_area_sqm"))
    if not matched_area or matched_area <= 0 or plot_area_sqm <= 0:
        return False
    min_ratio, max_ratio = DDA_VALUATION_SIZE_BAND
    ratio = matched_area / plot_area_sqm
    return min_ratio <= ratio <= max_ratio


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        transaction_id = str(item.get("transaction_id") or "")
        if transaction_id and transaction_id in seen:
            continue
        if transaction_id:
            seen.add(transaction_id)
        deduped.append(item)
    return deduped


def _select_plot_valuation_evidence(
    row: dict[str, Any], community_evidence: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str]:
    plot_number = str(row.get("plot_number") or "")
    plot_area_sqm = _float_or_none(row.get("plot_area_sqm")) or 0.0
    target_far_band = _far_band(_plot_far(row))

    same_plot = [
        item for item in community_evidence if str(item.get("plot_number") or "") == plot_number
    ]
    same_band = [
        item
        for item in community_evidence
        if item.get("far_band") == target_far_band and _evidence_size_match(item, plot_area_sqm)
    ]
    broader_band = [item for item in community_evidence if item.get("far_band") == target_far_band]

    candidates = _dedupe_evidence([*same_plot, *same_band])
    if same_plot and len(candidates) >= DDA_VALUATION_MIN_COMP_COUNT:
        return candidates, "matched plot and same-density comparable sales"
    if len(candidates) >= DDA_VALUATION_MIN_COMP_COUNT:
        return candidates, "same-community, same-density, size-matched sales"

    candidates = _dedupe_evidence([*candidates, *broader_band])
    if len(candidates) >= DDA_VALUATION_MIN_COMP_COUNT:
        return candidates, "same-community, same-density sales"

    candidates = _dedupe_evidence([*candidates, *community_evidence])
    if candidates:
        return candidates, "same-community land sales"
    return [], "no transaction evidence"


def _dda_plot_valuation(
    row: dict[str, Any],
    evidence_by_community: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    max_gfa_sqm = _float_or_none(row.get("max_gfa_sqm"))
    if not max_gfa_sqm or max_gfa_sqm <= 0:
        return _empty_dda_valuation("Max GFA not available.")

    community = _community_key(row.get("community_name"))
    community_evidence = (evidence_by_community or {}).get(community, [])
    evidence, basis = _select_plot_valuation_evidence(row, community_evidence)
    rate_range = _valuation_rate_range([float(item.get("rate_aed_sqft") or 0) for item in evidence])
    if not rate_range:
        return _empty_dda_valuation("DLD land-sale evidence unavailable for this community.")

    min_rate, max_rate = rate_range
    max_gfa_sqft = max_gfa_sqm * SQM_TO_SQFT
    confidence = "High" if len(evidence) >= 8 else "Medium" if len(evidence) >= 3 else "Low"
    note = f"{len(evidence)} DLD land sales; {basis}; rates are AED/sqft of matched DDA max GFA."
    return {
        "valuation_rate_min_aed_sqft": round(min_rate, 1),
        "valuation_rate_max_aed_sqft": round(max_rate, 1),
        "valuation_min_aed": round(max_gfa_sqft * min_rate),
        "valuation_max_aed": round(max_gfa_sqft * max_rate),
        "valuation_confidence": confidence,
        "valuation_note": note,
    }


def _dda_plot_indexes(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, list[Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        community = _community_key(row.get("community_name"))
        plot_area_sqm = _float_or_none(row.get("plot_area_sqm"))
        max_gfa_sqm = _float_or_none(row.get("max_gfa_sqm"))
        if not community or not plot_area_sqm or plot_area_sqm <= 0:
            continue
        if not max_gfa_sqm or max_gfa_sqm <= 0:
            continue
        plot = {
            "plot_number": row.get("plot_number"),
            "plot_area_sqm": plot_area_sqm,
            "max_gfa_sqm": max_gfa_sqm,
            "far": max_gfa_sqm / plot_area_sqm,
        }
        grouped.setdefault(community, []).append(plot)

    indexes: dict[str, dict[str, list[Any]]] = {}
    for community, plots in grouped.items():
        sorted_plots = sorted(plots, key=lambda item: item["plot_area_sqm"])
        indexes[community] = {
            "areas": [plot["plot_area_sqm"] for plot in sorted_plots],
            "plots": sorted_plots,
        }
    return indexes


def _nearest_dda_plot_by_area(
    index: dict[str, list[Any]], transaction_area_sqm: float
) -> dict[str, Any] | None:
    areas = index["areas"]
    plots = index["plots"]
    if not areas:
        return None
    insert_at = bisect_left(areas, transaction_area_sqm)
    candidates = []
    if insert_at < len(plots):
        candidates.append(plots[insert_at])
    if insert_at > 0:
        candidates.append(plots[insert_at - 1])
    if not candidates:
        return None
    return min(candidates, key=lambda plot: abs(plot["plot_area_sqm"] - transaction_area_sqm))


async def _dda_land_transaction_rows(communities: set[str]) -> list[dict[str, Any]]:
    if not communities:
        return []
    return await query(
        """
        SELECT
            transaction_id,
            instance_date,
            area_name_en,
            project_name_en,
            property_usage_en,
            procedure_name_en,
            toFloat64(procedure_area) AS plot_area_sqm,
            toFloat64(actual_worth) AS price_aed
        FROM ch_transactions
        WHERE trans_group_en = 'Sales'
          AND property_type_en = 'Land'
          AND actual_worth > {min_transaction_aed:Float64}
          AND procedure_area > 0
          AND instance_date >= today() - {lookback_days:Int32}
          AND has({communities:Array(String)}, lowerUTF8(area_name_en))
          AND has({procedures:Array(String)}, procedure_name_en)
        ORDER BY instance_date DESC
        LIMIT 100000
        """,
        {
            "communities": sorted(communities),
            "procedures": list(DDA_VALUATION_MARKET_PROCEDURES),
            "lookback_days": DDA_VALUATION_LOOKBACK_DAYS,
            "min_transaction_aed": DDA_VALUATION_MIN_TRANSACTION_AED,
        },
    )


def _transaction_evidence_by_community(
    transaction_rows: list[dict[str, Any]],
    plot_indexes: dict[str, dict[str, list[Any]]],
) -> dict[str, list[dict[str, Any]]]:
    evidence_by_community: dict[str, list[dict[str, Any]]] = {}
    for transaction in transaction_rows:
        community = _community_key(transaction.get("area_name_en"))
        index = plot_indexes.get(community)
        transaction_area = _float_or_none(transaction.get("plot_area_sqm"))
        price_aed = _float_or_none(transaction.get("price_aed"))
        if not index or not transaction_area or transaction_area <= 0:
            continue
        if not price_aed or price_aed <= 0:
            continue

        matched_plot = _nearest_dda_plot_by_area(index, transaction_area)
        if not matched_plot:
            continue
        matched_area = float(matched_plot["plot_area_sqm"])
        area_delta = abs(matched_area - transaction_area) / transaction_area
        if area_delta > DDA_VALUATION_MAX_PLOT_AREA_DELTA:
            continue

        max_gfa_sqm = float(matched_plot["max_gfa_sqm"])
        rate = price_aed / (max_gfa_sqm * SQM_TO_SQFT)
        if not math.isfinite(rate) or rate <= 0:
            continue

        evidence_by_community.setdefault(community, []).append(
            {
                "transaction_id": transaction.get("transaction_id"),
                "transaction_date": transaction.get("instance_date"),
                "plot_number": matched_plot.get("plot_number"),
                "matched_plot_area_sqm": matched_area,
                "matched_max_gfa_sqm": max_gfa_sqm,
                "far": matched_plot["far"],
                "far_band": _far_band(matched_plot["far"]),
                "rate_aed_sqft": rate,
                "price_aed": price_aed,
                "project_name": transaction.get("project_name_en") or "",
                "procedure_name": transaction.get("procedure_name_en") or "",
                "area_delta_pct": area_delta * 100,
            }
        )
    return evidence_by_community


async def _dda_transaction_valuation_lookup(
    target_rows: list[dict[str, Any]], all_plot_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    community_names = {
        str(row.get("community_name") or "").strip().lower()
        for row in target_rows
        if str(row.get("community_name") or "").strip()
    }
    if not community_names:
        return {}
    plot_indexes = _dda_plot_indexes(all_plot_rows)
    transaction_rows = await _dda_land_transaction_rows(community_names)
    evidence_by_community = _transaction_evidence_by_community(transaction_rows, plot_indexes)
    return {
        str(row.get("plot_number") or ""): _dda_plot_valuation(row, evidence_by_community)
        for row in target_rows
    }


async def get_dda_plots_for_area(
    area: str | None = None,
    limit: int = 300,
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    include_valuations: bool = False,
) -> list[DDAPlotFeature]:
    """Return DDA GIS plot polygons for a community or current map bounds."""
    has_bounds = all(value is not None for value in (west, south, east, north))
    area_query = area.strip().lower() if area else ""
    rows = await _get_dda_plot_geometries()
    target_rows: list[dict[str, Any]] = []
    for row in rows:
        if (
            area_query
            and area_query not in " ".join([row["community_name"], row["project_name"]]).lower()
        ):
            continue
        if has_bounds and not _bounds_intersects(
            row["bounds"],
            west=west or 0,
            south=south or 0,
            east=east or 0,
            north=north or 0,
        ):
            continue
        target_rows.append(row)
        if len(target_rows) >= limit:
            break

    valuations = (
        await _dda_transaction_valuation_lookup(target_rows, rows) if include_valuations else {}
    )
    results: list[DDAPlotFeature] = []
    for row in target_rows:
        if include_valuations:
            valuation = valuations.get(str(row.get("plot_number") or "")) or _dda_plot_valuation(
                row
            )
        else:
            valuation = _empty_dda_valuation("Valuation deferred for bulk map rendering.")
        results.append(
            DDAPlotFeature(
                plot_number=row["plot_number"],
                project_name=row["project_name"],
                community_name=row["community_name"],
                plot_area_sqm=row["plot_area_sqm"],
                coordinates=row["coordinates"],
                land_use_summary=row["land_use_summary"],
                max_gfa_sqm=row["max_gfa_sqm"],
                max_height=row["max_height"],
                max_coverage=row["max_coverage"],
                land_use=row["land_use"],
                gfa_type=row["gfa_type"],
                is_verified=row["is_verified"],
                development_status=row.get("development_status", "no_observed_asset"),
                development_confidence=row.get("development_confidence", "low"),
                development_method=row.get("development_method", "no_observed_asset"),
                development_note=row.get("development_note"),
                linked_asset_count=int(row.get("linked_asset_count") or 0),
                linked_physical_asset_count=int(row.get("linked_physical_asset_count") or 0),
                subdivision_plot_count=int(row.get("subdivision_plot_count") or 0),
                subdivision_confirmed_count=int(row.get("subdivision_confirmed_count") or 0),
                **valuation,
            )
        )
    return results
