import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Literal

from app.clickhouse.client import query
from app.feasibility.models import (
    ComparableData,
    ComparableProject,
    GISLandUse,
    LandSaleEvidence,
    MarketPricingRow,
    OffPlanPricingConfidence,
    OffPlanPricingRow,
    OffPlanUnitPricingBenchmark,
    Plot,
    PlotDetails,
    RentalRateBySizeBand,
    UnitTypeData,
    Usage,
)

logger = logging.getLogger(__name__)

Stage = Literal["existing", "off_plan", "upcoming", "all"]

RESIDENTIAL_TYPES = ["studio", "1br", "2br", "3br", "4br", "4br+", "villa", "townhouse"]
COMMERCIAL_TYPES = ["office", "retail", "industrial", "hospitality"]


def normalize_whitespace(value: str) -> str:
    return " ".join((value or "").strip().split())


def normalize_unit_type(value: str) -> str:
    raw = normalize_whitespace(value).lower()
    if not raw or raw in {"na", "n/a", "unknown"}:
        return "other"

    patterns = [
        (r"^studio$", "studio"),
        (r"^(1|one)\s*(b\/r|br|bed(room)?s?\+?hall?)$", "1br"),
        (r"^(2|two)\s*(b\/r|br|bed(room)?s?\+?hall?)$", "2br"),
        (r"^(3|three)\s*(b\/r|br|bed(room)?s?\+?hall?)$", "3br"),
        (r"^(4|four)\s*(b\/r|br|bed(room)?s?\+?hall?)$", "4br"),
        (r"^(5|six|7|8|9|10|\d+)\s*(b\/r|br|bed(room)?s?\+?hall?)$", "4br+"),
        (r"penthouse", "4br+"),
        (r"villa", "villa"),
        (r"townhouse", "townhouse"),
        (r"office", "office"),
        (r"shop|retail|store|showroom|kiosk|restaurant", "retail"),
        (
            r"warehouse|workshop|industrial|factory|labor camp|staff accommod",
            "industrial",
        ),
        (r"hotel", "hospitality"),
    ]
    normalized = re.sub(r"[\s\-_/]+", "", raw)
    for pattern, canonical in patterns:
        if re.search(pattern, raw) or re.search(pattern, normalized):
            return canonical
    return "other"


def infer_usage_from_plot(
    land_use_values: list[str], gfa_type: str, general_notes: list[str]
) -> Usage:
    haystack = " ".join(
        [
            *(land_use_values or []),
            gfa_type or "",
            *(general_notes or []),
        ]
    ).lower()
    has_res = any(
        token in haystack
        for token in ["residential", "villa", "apartment", "townhouse", "dwelling"]
    )
    has_com = any(
        token in haystack
        for token in [
            "commercial",
            "office",
            "retail",
            "shopping center",
            "shop",
            "hotel",
            "hospitality",
            "warehouse",
            "industrial",
        ]
    )
    if has_res and has_com:
        return "mixed_use"
    if has_res:
        return "residential"
    if has_com:
        return "commercial"
    return "unknown"


def normalize_project_stage(value: str) -> Stage:
    raw = normalize_whitespace(value).upper()
    if raw in {"FINISHED"}:
        return "existing"
    if raw in {"ACTIVE"}:
        return "off_plan"
    if raw in {"NOT_STARTED", "PENDING", "CONDITIONAL_ACTIVATING"}:
        return "upcoming"
    return "all"


def transaction_usage_clause(usage: Usage, column: str = "property_usage_en") -> str:
    if usage == "residential":
        return f"({column} IN ('Residential', 'Hospitality ', 'Hospitality'))"
    if usage == "commercial":
        return f"({column} IN ('Commercial', 'Industrial', 'Storage'))"
    if usage == "mixed_use":
        return f"({column} IN ('Residential / Commercial', 'Multi-Use', 'Industrial / Commercial', 'Industrial / Commercial / Residential'))"
    return "1 = 1"


def land_sale_usage_clause(usage: Usage, column: str = "property_usage_en") -> str:
    if usage == "residential":
        return f"{column} = 'Residential'"
    if usage == "commercial":
        return f"({column} IN ('Commercial', 'Industrial', 'Storage', 'Industrial / Commercial'))"
    if usage == "mixed_use":
        return (
            f"({column} IN ('Residential / Commercial', 'Multi-Use', "
            "'Industrial / Commercial', 'Industrial / Commercial / Residential'))"
        )
    return "1 = 1"


def transaction_stage_clause(stage: Stage, column: str = "reg_type_en") -> str:
    if stage == "existing":
        return f"{column} = 'Existing Properties'"
    if stage == "off_plan":
        return f"{column} = 'Off-Plan Properties'"
    return "1 = 1"


def canonical_unit_type_case_sql(column: str = "rooms_en") -> str:
    return f"""
    multiIf(
        match(lowerUTF8(trimBoth({column})), '^studio$'), 'studio',
        match(lowerUTF8(trimBoth({column})), '^(1|one)\\s*(b/r|br|bed(room)?s?\\+?hall?)$'), '1br',
        match(lowerUTF8(trimBoth({column})), '^(2|two)\\s*(b/r|br|bed(room)?s?\\+?hall?)$'), '2br',
        match(lowerUTF8(trimBoth({column})), '^(3|three)\\s*(b/r|br|bed(room)?s?\\+?hall?)$'), '3br',
        match(lowerUTF8(trimBoth({column})), '^(4|four)\\s*(b/r|br|bed(room)?s?\\+?hall?)$'), '4br',
        match(lowerUTF8(trimBoth({column})), '^(5|6|7|8|9|10|\\d+)\\s*(b/r|br|bed(room)?s?\\+?hall?)$'), '4br+',
        match(lowerUTF8(trimBoth({column})), 'penthouse'), '4br+',
        match(lowerUTF8(trimBoth({column})), 'villa'), 'villa',
        match(lowerUTF8(trimBoth({column})), 'townhouse'), 'townhouse',
        match(lowerUTF8(trimBoth({column})), 'office'), 'office',
        match(lowerUTF8(trimBoth({column})), 'shop|retail|store|showroom|kiosk|restaurant'), 'retail',
        match(lowerUTF8(trimBoth({column})), 'warehouse|workshop|industrial|factory|labor camp|staff accommod'), 'industrial',
        match(lowerUTF8(trimBoth({column})), 'hotel'), 'hospitality',
        'other'
    )
    """


def months_between(start: datetime, end: datetime) -> int:
    return max((end.year - start.year) * 12 + (end.month - start.month), 0)


def _label_confidence(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def score_off_plan_row(
    row: OffPlanPricingRow,
    target_horizon_months: int,
    *,
    now: datetime | None = None,
) -> dict[str, float]:
    valuation_date = now or datetime.now(timezone.utc)
    horizon_distance = abs(row.avg_months_to_completion - target_horizon_months)
    sample_score = min(row.transaction_count / 15, 1.0)
    horizon_score = max(0.0, 1 - (horizon_distance / 24))
    last_transaction = _parse_date(row.last_transaction_date)
    if last_transaction is None:
        recency_score = 0.25
    else:
        months_since_trade = months_between(last_transaction, valuation_date)
        recency_score = max(0.0, 1 - (months_since_trade / 24))
    confidence_score = round(
        ((sample_score * 0.45) + (horizon_score * 0.35) + (recency_score * 0.20)) * 100,
        1,
    )
    return {
        "sample_score": round(sample_score * 100, 1),
        "horizon_score": round(horizon_score * 100, 1),
        "recency_score": round(recency_score * 100, 1),
        "confidence_score": confidence_score,
    }


def build_off_plan_pricing_confidence(
    rows: list[OffPlanPricingRow],
    target_horizon_months: int,
    *,
    now: datetime | None = None,
) -> OffPlanPricingConfidence | None:
    if not rows:
        return None
    scored_rows = [(row, score_off_plan_row(row, target_horizon_months, now=now)) for row in rows]
    scored_rows.sort(key=lambda item: (-item[1]["confidence_score"], -item[0].transaction_count))
    top_rows = scored_rows[: min(3, len(scored_rows))]
    weight_total = sum(max(row.transaction_count, 1) for row, _ in top_rows)
    sample_score = round(
        sum(scores["sample_score"] * max(row.transaction_count, 1) for row, scores in top_rows)
        / weight_total,
        1,
    )
    horizon_score = round(
        sum(scores["horizon_score"] * max(row.transaction_count, 1) for row, scores in top_rows)
        / weight_total,
        1,
    )
    recency_score = round(
        sum(scores["recency_score"] * max(row.transaction_count, 1) for row, scores in top_rows)
        / weight_total,
        1,
    )
    confidence_score = round(
        sum(scores["confidence_score"] * max(row.transaction_count, 1) for row, scores in top_rows)
        / weight_total,
        1,
    )
    matched_transactions = sum(row.transaction_count for row, _ in top_rows)
    return OffPlanPricingConfidence(
        target_horizon_months=target_horizon_months,
        matched_transactions=matched_transactions,
        confidence_score=confidence_score,
        confidence_label=_label_confidence(confidence_score),  # type: ignore[arg-type]
        sample_score=sample_score,
        horizon_score=horizon_score,
        recency_score=recency_score,
        note=(
            f"Best off-plan evidence covers {matched_transactions} transactions across "
            f"{len(top_rows)} bucket(s)."
        ),
    )


def build_off_plan_unit_benchmarks(
    rows: list[OffPlanPricingRow],
    target_horizon_months: int,
    fallback_prices: dict[str, float],
    *,
    now: datetime | None = None,
) -> list[OffPlanUnitPricingBenchmark]:
    benchmarks: list[OffPlanUnitPricingBenchmark] = []
    unit_types = sorted({row.unit_type for row in rows} | set(fallback_prices.keys()))
    for unit_type in unit_types:
        unit_rows = [row for row in rows if row.unit_type == unit_type]
        if unit_rows:
            scored = [
                (row, score_off_plan_row(row, target_horizon_months, now=now)) for row in unit_rows
            ]
            scored.sort(key=lambda item: (-item[1]["confidence_score"], -item[0].transaction_count))
            selected, scores = scored[0]
            benchmarks.append(
                OffPlanUnitPricingBenchmark(
                    unit_type=unit_type,
                    selected_horizon_bucket=selected.horizon_bucket,
                    avg_months_to_completion=selected.avg_months_to_completion,
                    transaction_count=selected.transaction_count,
                    selected_price_sqm=selected.median_price_sqm,
                    fallback_used=False,
                    confidence_score=scores["confidence_score"],
                    confidence_label=_label_confidence(scores["confidence_score"]),  # type: ignore[arg-type]
                    sample_score=scores["sample_score"],
                    horizon_score=scores["horizon_score"],
                    recency_score=scores["recency_score"],
                    last_transaction_date=selected.last_transaction_date,
                    note=(
                        f"Selected {selected.horizon_bucket} for {unit_type} with "
                        f"{selected.transaction_count} transactions."
                    ),
                )
            )
        elif unit_type in fallback_prices:
            benchmarks.append(
                OffPlanUnitPricingBenchmark(
                    unit_type=unit_type,
                    selected_horizon_bucket="fallback",
                    avg_months_to_completion=float(target_horizon_months),
                    transaction_count=0,
                    selected_price_sqm=fallback_prices[unit_type],
                    fallback_used=True,
                    confidence_score=20.0,
                    confidence_label="low",
                    sample_score=0.0,
                    horizon_score=0.0,
                    recency_score=0.0,
                    last_transaction_date=None,
                    note="No matching off-plan transactions for this unit type; existing-sales fallback was used.",
                )
            )
    return benchmarks


def _parse_land_use(raw: str) -> list[GISLandUse]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [
            GISLandUse(
                type=str(item.get("type", "")).strip(),
                use=str(item.get("use", "")).strip(),
            )
            for item in parsed
            if item.get("type") or item.get("use")
        ]
    except Exception:
        return []


def _parse_notes(raw: str) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(" | ") if part.strip()]


def _coordinate_pair(raw: object) -> list[float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        x = float(raw[0])  # type: ignore[index]
        y = float(raw[1])  # type: ignore[index]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return [x, y]


def _extract_coordinate_pairs(raw: object) -> list[list[float]]:
    pair = _coordinate_pair(raw)
    if pair is not None:
        return [pair]
    if not isinstance(raw, (list, tuple)):
        return []
    coords: list[list[float]] = []
    for item in raw:
        coords.extend(_extract_coordinate_pairs(item))
    return coords


def _parse_coordinates(raw: object) -> list[list[float]]:
    if raw in (None, "", "[]"):
        return []
    parsed: object = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(parsed, dict):
        parsed = parsed.get("coordinates", [])
    coords = _extract_coordinate_pairs(parsed)
    if len(coords) >= 2 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return coords


def _build_setbacks(row: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for side in range(1, 5):
        building = str(row.get(f"side{side}_building") or "").strip()
        podium = str(row.get(f"side{side}_podium") or "").strip()
        if building:
            result[f"side{side}_building"] = building
        if podium:
            result[f"side{side}_podium"] = podium
    return result


def _build_plot_warnings(row: dict[str, Any], far: float | None, notes: list[str]) -> list[str]:
    warnings: list[str] = []
    if not row.get("is_verified"):
        warnings.append("GIS plot is not marked as verified.")
    if not row.get("max_gfa_sqm"):
        warnings.append("Maximum GFA is missing, so HBU fit is lower confidence.")
    if row.get("site_plan_expiry_date"):
        warnings.append(f"Site plan expiry date: {row['site_plan_expiry_date']}.")
    if row.get("max_height", "").upper() == "SEE NOTES":
        warnings.append("Maximum height is defined in notes instead of a structured field.")
    if row.get("max_coverage", "").upper() == "SEE NOTES":
        warnings.append("Maximum coverage is defined in notes instead of a structured field.")
    if far and far > 12:
        warnings.append("Derived FAR is unusually high; confirm the GIS record manually.")
    if any("NOC" in note.upper() for note in notes):
        warnings.append("General notes include authority or third-party NOC requirements.")
    return warnings


def _dominant_type(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    return str(rows[0].get("unit_type") or rows[0].get("dominant_unit_type") or "").strip() or None


async def get_areas() -> list[str]:
    """Get distinct transaction areas with sales activity."""
    sql = """
    SELECT area_name_en
    FROM ch_transactions
    WHERE trans_group_en = 'Sales'
      AND area_name_en != ''
    GROUP BY area_name_en
    ORDER BY count() DESC, area_name_en
    """
    rows = await query(sql, {})
    return [r["area_name_en"] for r in rows]


async def resolve_market_area(name: str) -> str:
    if not name:
        return name
    sql = """
    SELECT area_name_en
    FROM ch_transactions
    WHERE trans_group_en = 'Sales'
      AND area_name_en ILIKE {pattern:String}
    GROUP BY area_name_en
    ORDER BY (lower(area_name_en) = lower({name:String})) DESC, count() DESC
    LIMIT 1
    """
    rows = await query(sql, {"name": name, "pattern": f"%{name}%"})
    return rows[0]["area_name_en"] if rows else name


async def search_plots(
    q: str = "",
    community: str = "",
    min_plot_area_sqm: float | None = None,
    max_plot_area_sqm: float | None = None,
    offset: int = 0,
    limit: int = 200,
) -> list[Plot]:
    where = ["plot_number != ''"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if q:
        where.append(
            "(plot_number ILIKE {q:String} OR project_name ILIKE {q:String} OR community_name ILIKE {q:String})"
        )
        params["q"] = f"%{q}%"
    if community:
        where.append(
            "lowerUTF8(trimBoth(community_name)) = lowerUTF8(trimBoth({community:String}))"
        )
        params["community"] = community
    if min_plot_area_sqm is not None:
        where.append("plot_area_sqm >= {min_plot_area_sqm:Float64}")
        params["min_plot_area_sqm"] = min_plot_area_sqm
    if max_plot_area_sqm is not None:
        where.append("plot_area_sqm <= {max_plot_area_sqm:Float64}")
        params["max_plot_area_sqm"] = max_plot_area_sqm

    sql = f"""
    SELECT
        plot_number,
        community_name,
        project_name,
        plot_area_sqm,
        max_gfa_sqm,
        max_height,
        max_coverage,
        gfa_type,
        is_verified,
        land_use
    FROM ch_gis_land_plots
    WHERE {" AND ".join(where)}
    ORDER BY is_verified DESC, plot_area_sqm DESC
    LIMIT {{limit:UInt32}}
    OFFSET {{offset:UInt32}}
    """
    rows = await query(sql, params)
    plots: list[Plot] = []
    for row in rows:
        land_use = _parse_land_use(row.get("land_use", ""))
        plots.append(
            Plot(
                plot_number=row["plot_number"],
                community_name=row.get("community_name") or "",
                project_name=row.get("project_name") or "",
                plot_area_sqm=float(row.get("plot_area_sqm") or 0),
                max_gfa_sqm=float(row.get("max_gfa_sqm") or 0),
                max_height=row.get("max_height") or "",
                max_coverage=row.get("max_coverage") or "",
                gfa_type=row.get("gfa_type") or "",
                is_verified=bool(row.get("is_verified")),
                land_use_summary=[f"{item.type}: {item.use}" for item in land_use[:3]],
            )
        )
    return plots


async def list_communities(limit: int = 5000) -> list[str]:
    sql = """
    SELECT community_name
    FROM ch_gis_land_plots
    WHERE community_name != ''
    GROUP BY community_name
    ORDER BY count() DESC, community_name
    LIMIT {limit:UInt32}
    """
    rows = await query(sql, {"limit": limit})
    return [r["community_name"] for r in rows]


async def get_plot_details(plot_number: str) -> PlotDetails | None:
    sql = """
    SELECT *
    FROM ch_gis_land_plots
    WHERE plot_number = {plot_number:String}
    LIMIT 1
    """
    rows = await query(sql, {"plot_number": plot_number})
    if not rows:
        return None

    row = rows[0]
    plot_area_sqm = float(row.get("plot_area_sqm") or 0)
    max_gfa_sqm = float(row.get("max_gfa_sqm") or 0)
    far = round(max_gfa_sqm / plot_area_sqm, 2) if plot_area_sqm > 0 and max_gfa_sqm > 0 else None
    land_use = _parse_land_use(row.get("land_use", ""))
    notes = _parse_notes(row.get("general_notes", ""))
    inferred_usage = infer_usage_from_plot(
        [f"{item.type} {item.use}" for item in land_use],
        str(row.get("gfa_type") or ""),
        notes,
    )
    return PlotDetails(
        plot_number=row["plot_number"],
        community_name=row.get("community_name") or "",
        project_name=row.get("project_name") or "",
        master_developer=(row.get("master_developer") or None),
        plot_area_sqm=plot_area_sqm,
        max_gfa_sqm=max_gfa_sqm,
        max_gfa_sqft=float(row.get("max_gfa_sqft") or 0),
        max_height=row.get("max_height") or "",
        max_coverage=row.get("max_coverage") or "",
        gfa_type=row.get("gfa_type") or "",
        far=far,
        inferred_usage=inferred_usage,
        site_plan_issue_date=str(row.get("site_plan_issue_date"))
        if row.get("site_plan_issue_date")
        else None,
        site_plan_expiry_date=str(row.get("site_plan_expiry_date"))
        if row.get("site_plan_expiry_date")
        else None,
        is_verified=bool(row.get("is_verified")),
        verify_comments=(row.get("verify_comments") or None),
        land_use=land_use,
        general_notes=notes,
        setbacks=_build_setbacks(row),
        coordinates=_parse_coordinates(row.get("coordinates", "")),
        warnings=_build_plot_warnings(row, far, notes),
    )


async def get_market_pricing(
    area_name: str,
    usage: Usage,
    stage: Stage = "existing",
    days: int = 365,
) -> list[MarketPricingRow]:
    canonical_unit_sql = canonical_unit_type_case_sql("rooms_en")
    where = [
        "trans_group_en = 'Sales'",
        "meter_sale_price > 0",
        "lower(area_name_en) = lower({area_name:String})",
        transaction_usage_clause(usage),
        transaction_stage_clause(stage),
        "instance_date >= today() - {days:Int32}",
    ]
    sql = f"""
    SELECT
        {canonical_unit_sql} AS unit_type,
        count() AS transaction_count,
        round(median(meter_sale_price), 0) AS median_price_sqm,
        round(avg(procedure_area), 0) AS avg_area_sqm
    FROM ch_transactions
    WHERE {" AND ".join(where)}
    GROUP BY unit_type
    HAVING unit_type != 'other'
    ORDER BY transaction_count DESC
    """
    rows = await query(sql, {"area_name": area_name, "days": days})
    return [
        MarketPricingRow(
            unit_type=row["unit_type"],
            transaction_count=int(row["transaction_count"]),
            median_price_sqm=float(row["median_price_sqm"]),
            avg_area_sqm=float(row["avg_area_sqm"]) if row.get("avg_area_sqm") else None,
        )
        for row in rows
    ]


async def get_off_plan_pricing_curve(
    area_name: str,
    usage: Usage,
    target_handover_date: str | None,
    days: int = 1095,
) -> list[OffPlanPricingRow]:
    now = datetime.now(timezone.utc)
    try:
        target_handover = (
            datetime.fromisoformat(target_handover_date).replace(tzinfo=timezone.utc)
            if target_handover_date
            else now
        )
    except ValueError:
        target_handover = now
    target_horizon_months = max(months_between(now, target_handover), 0)
    canonical_unit_sql = canonical_unit_type_case_sql("t.rooms_en")
    sql = f"""
    SELECT
        {canonical_unit_sql} AS unit_type,
        multiIf(
            months_to_completion <= 12, '0-12m',
            months_to_completion <= 24, '13-24m',
            months_to_completion <= 36, '25-36m',
            '37m+'
        ) AS horizon_bucket,
        round(avg(months_to_completion), 1) AS avg_months_to_completion,
        count() AS transaction_count,
        round(median(t.meter_sale_price), 0) AS median_price_sqm,
        round(avg(t.procedure_area), 0) AS avg_area_sqm,
        toString(max(toDate(t.instance_date))) AS last_transaction_date
    FROM (
        SELECT
            t.*,
            greatest(
                dateDiff('month', toDate(t.instance_date), toDate(p.completion_date)),
                0
            ) AS months_to_completion
        FROM ch_transactions t
        INNER JOIN ch_projects p
            ON lowerUTF8(trimBoth(p.project_name_en)) = lowerUTF8(trimBoth(t.project_name_en))
        WHERE t.trans_group_en = 'Sales'
          AND t.meter_sale_price > 0
          AND lower(t.area_name_en) = lower({{area_name:String}})
          AND {transaction_usage_clause(usage, "t.property_usage_en")}
          AND {transaction_stage_clause("off_plan", "t.reg_type_en")}
          AND t.instance_date >= today() - {{days:Int32}}
          AND p.completion_date IS NOT NULL
    ) t
    GROUP BY unit_type, horizon_bucket
    HAVING unit_type != 'other'
    ORDER BY
        abs(avg_months_to_completion - {{target_horizon_months:Int32}}) ASC,
        transaction_count DESC
    """
    rows = await query(
        sql,
        {
            "area_name": area_name,
            "days": days,
            "target_horizon_months": target_horizon_months,
        },
    )
    return [
        OffPlanPricingRow(
            unit_type=row["unit_type"],
            horizon_bucket=row["horizon_bucket"],
            avg_months_to_completion=float(row.get("avg_months_to_completion") or 0),
            transaction_count=int(row["transaction_count"]),
            median_price_sqm=float(row["median_price_sqm"]),
            avg_area_sqm=float(row["avg_area_sqm"]) if row.get("avg_area_sqm") else None,
            last_transaction_date=row.get("last_transaction_date"),
        )
        for row in rows
    ]


async def get_rental_rates_by_size_band(
    area_name: str,
    days: int = 365,
) -> list[RentalRateBySizeBand]:
    size_bands = [
        ("studio", "< 55 sqm", 0, 55),
        ("1br", "55–90 sqm", 55, 90),
        ("2br", "90–140 sqm", 90, 140),
        ("3br", "140–200 sqm", 140, 200),
        ("4br+", "> 200 sqm", 200, 99999),
    ]
    results: list[RentalRateBySizeBand] = []
    for unit_type, label, lo, hi in size_bands:
        sql = """
        SELECT
            median(toFloat64(annual_amount) / greatest(toFloat64(actual_area), 1)) AS median_rent_psm_annual,
            median(toFloat64(annual_amount)) AS median_annual_rent,
            count() AS contract_count
        FROM ch_rent_contracts
        WHERE lower(area_name_en) = lower({area_name:String})
          AND actual_area > {lo:Float64}
          AND actual_area <= {hi:Float64}
          AND annual_amount > 0
          AND contract_start_date >= today() - {days:Int32}
        """
        rows = await query(
            sql, {"area_name": area_name, "lo": float(lo), "hi": float(hi), "days": days}
        )
        if rows and int(rows[0].get("contract_count") or 0) >= 5:
            results.append(
                RentalRateBySizeBand(
                    unit_type_proxy=unit_type,
                    size_band_label=label,
                    median_rent_psm_annual=float(rows[0]["median_rent_psm_annual"] or 0),
                    median_annual_rent=float(rows[0]["median_annual_rent"] or 0),
                    contract_count=int(rows[0]["contract_count"]),
                )
            )
    return results


async def get_land_sale_evidence(
    area_name: str,
    plot_area_sqm: float | None = None,
    usage: Usage | None = None,
    target_far: float | None = None,
    days: int = 1825,
    limit: int = 12,
) -> list[LandSaleEvidence]:
    base_where = [
        "trans_group_en = 'Sales'",
        "property_type_en = 'Land'",
        "actual_worth > 0",
        "procedure_area > 0",
        "lower(area_name_en) = lower({area_name:String})",
        "instance_date >= today() - {days:Int32}",
    ]
    if plot_area_sqm and plot_area_sqm > 0:
        base_where.append("procedure_area BETWEEN {min_area:Float64} AND {max_area:Float64}")
        min_area = plot_area_sqm * 10.764 * 0.5
        max_area = plot_area_sqm * 10.764 * 1.75
    else:
        min_area = None
        max_area = None

    params: dict[str, Any] = {
        "area_name": area_name,
        "days": days,
        "limit": limit,
        "target_area": (plot_area_sqm or 0) * 10.764,
    }
    if min_area is not None and max_area is not None:
        params["min_area"] = min_area
        params["max_area"] = max_area

    async def fetch_rows(where: list[str]) -> list[dict[str, Any]]:
        sql = f"""
        SELECT
            transaction_id,
            instance_date,
            area_name_en,
            project_name_en,
            procedure_name_en,
            property_usage_en,
            round(toFloat64(procedure_area) * 0.092903, 1) AS plot_area_sqm,
            toFloat64(actual_worth) AS price_aed,
            round(toFloat64(actual_worth) / greatest(toFloat64(procedure_area) * 0.092903, 1), 0) AS price_sqm,
            nullIf(nearest_landmark_en, '') AS nearest_landmark
        FROM ch_transactions
        WHERE {" AND ".join(where)}
        ORDER BY
            instance_date DESC,
            abs(toFloat64(procedure_area) - {{target_area:Float64}}) ASC
        LIMIT {{limit:Int32}}
        """
        return await query(sql, params)

    rows: list[dict[str, Any]] = []
    if usage and usage != "unknown":
        rows = await fetch_rows([*base_where, land_sale_usage_clause(usage)])
    if not rows:
        rows = await fetch_rows(base_where)

    def _price_per_gfa(price_aed: float, comp_plot_sqm: float) -> float | None:
        if target_far and target_far > 0 and comp_plot_sqm > 0 and price_aed > 0:
            return round(price_aed / (comp_plot_sqm * target_far), 0)
        return None

    return [
        LandSaleEvidence(
            transaction_id=row["transaction_id"],
            instance_date=str(row["instance_date"]),
            area_name=row["area_name_en"],
            project_name=row.get("project_name_en") or "",
            procedure_name=row.get("procedure_name_en") or "",
            property_usage=row.get("property_usage_en") or "",
            plot_area_sqm=float(row.get("plot_area_sqm") or 0),
            price_aed=float(row.get("price_aed") or 0),
            price_sqm=float(row.get("price_sqm") or 0),
            price_per_gfa_sqm=_price_per_gfa(
                float(row.get("price_aed") or 0),
                float(row.get("plot_area_sqm") or 0),
            ),
            nearest_landmark=row.get("nearest_landmark"),
        )
        for row in rows
    ]


async def _project_unit_mix(project_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not project_ids:
        return {}
    canonical_unit_sql = canonical_unit_type_case_sql("rooms_en")
    sql = f"""
    SELECT
        project_id,
        {canonical_unit_sql} AS unit_type,
        count() AS cnt,
        round(avg(actual_area), 1) AS avg_area_sqm
    FROM ch_units
    WHERE project_id IN ({{project_ids:Array(Int32)}})
      AND actual_area > 0
    GROUP BY project_id, unit_type
    HAVING unit_type != 'other'
    ORDER BY project_id, cnt DESC
    """
    rows = await query(sql, {"project_ids": project_ids})
    result: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(int(row["project_id"]), []).append(row)
    return result


async def rank_plot_comparables(
    plot: PlotDetails,
    usage: Usage,
    comparison_type: str,
    limit: int = 5,
) -> list[ComparableProject]:
    market_area = await resolve_market_area(plot.community_name)
    params = {"market_area": market_area}
    sql = """
    WITH land AS (
        SELECT
            p.project_id,
            sum(toFloat64(t.procedure_area)) AS total_land_area_sqm
        FROM ch_transactions t
        INNER JOIN ch_projects p ON p.project_number = t.project_number
        WHERE t.property_type_en = 'Land'
          AND t.trans_group_en = 'Sales'
          AND t.procedure_area > 0
          AND t.project_number != ''
        GROUP BY p.project_id
    )
    SELECT
        p.project_id,
        any(p.project_name_en) AS project_name,
        any(p.area_name_en) AS area_name,
        any(p.project_status) AS project_status,
        any(p.no_of_buildings) AS no_of_buildings,
        any(p.no_of_units) AS no_of_units,
        any(land.total_land_area_sqm) AS total_land_area_sqm
    FROM ch_projects p
    LEFT JOIN land ON p.project_id = land.project_id
    WHERE p.area_name_en = {market_area:String}
      AND p.project_name_en != ''
    GROUP BY p.project_id
    LIMIT 250
    """
    project_rows = await query(sql, params)
    project_ids = [int(row["project_id"]) for row in project_rows]
    unit_mix_by_project = await _project_unit_mix(project_ids)

    price_by_project: dict[int, float] = {}
    dominant_type_by_project: dict[int, str] = {}
    if comparison_type == "pricing":
        canonical_unit_sql = canonical_unit_type_case_sql("rooms_en")
        pricing_sql = f"""
        SELECT
            p.project_id AS project_id,
            round(median(t.meter_sale_price), 0) AS median_price_sqm,
            argMax(unit_type, cnt) AS dominant_unit_type
        FROM (
            SELECT
                project_name_en,
                {canonical_unit_sql} AS unit_type,
                count() AS cnt,
                meter_sale_price
            FROM ch_transactions
            WHERE trans_group_en = 'Sales'
              AND area_name_en = {{market_area:String}}
              AND {transaction_usage_clause(usage)}
              AND {transaction_stage_clause("existing")}
              AND meter_sale_price > 0
            GROUP BY project_name_en, unit_type, meter_sale_price
        ) t
        INNER JOIN ch_projects p ON p.project_name_en = t.project_name_en
        GROUP BY p.project_id
        """
        for row in await query(pricing_sql, {"market_area": market_area}):
            price_by_project[int(row["project_id"])] = float(row["median_price_sqm"])
            dominant_type_by_project[int(row["project_id"])] = row.get("dominant_unit_type") or ""

    scored: list[ComparableProject] = []
    target_area = plot.plot_area_sqm
    for row in project_rows:
        project_id = int(row["project_id"])
        total_land_area = (
            float(row["total_land_area_sqm"]) if row.get("total_land_area_sqm") else None
        )
        if comparison_type == "pricing" and project_id not in price_by_project:
            continue

        stage = normalize_project_stage(str(row.get("project_status") or ""))
        if comparison_type == "pipeline" and stage not in {"off_plan", "upcoming"}:
            continue

        unit_rows = unit_mix_by_project.get(project_id, [])
        dominant_type = dominant_type_by_project.get(project_id) or _dominant_type(unit_rows)
        if usage == "residential" and dominant_type and dominant_type not in RESIDENTIAL_TYPES:
            continue
        if usage == "commercial" and dominant_type and dominant_type not in COMMERCIAL_TYPES:
            continue

        score = 100.0
        rationale = [f"Same market area: {market_area}."]
        delta_pct = None
        if total_land_area and target_area > 0:
            delta_pct = abs(total_land_area - target_area) / target_area
            score -= min(delta_pct * 40, 45)
            rationale.append(f"Land area delta {round(delta_pct * 100, 1)}%.")
        else:
            score -= 25
            rationale.append("Missing derived land area.")

        if comparison_type == "pricing":
            rationale.append("Has existing transaction evidence.")
        else:
            rationale.append(f"Pipeline status: {row.get('project_status') or 'Unknown'}.")
            if stage == "upcoming":
                score += 5

        if dominant_type:
            rationale.append(f"Dominant unit type: {dominant_type}.")

        scored.append(
            ComparableProject(
                project_id=project_id,
                project_name=row.get("project_name") or f"Project {project_id}",
                area_name=row.get("area_name") or market_area,
                project_status=row.get("project_status") or None,
                comparison_type="pricing" if comparison_type == "pricing" else "pipeline",
                score=round(score, 1),
                total_land_area_sqm=round(total_land_area, 0) if total_land_area else None,
                land_area_delta_pct=round(delta_pct * 100, 1) if delta_pct is not None else None,
                no_of_buildings=int(row["no_of_buildings"])
                if row.get("no_of_buildings") is not None
                else None,
                no_of_units=int(row["no_of_units"]) if row.get("no_of_units") is not None else None,
                median_price_sqm=price_by_project.get(project_id),
                dominant_unit_type=dominant_type,
                rationale=rationale,
            )
        )

    scored.sort(key=lambda item: (-item.score, item.land_area_delta_pct or 9999))
    return scored[:limit]


async def get_land_plots(area: str, size_sqm: float, tolerance: float = 0.25) -> list[Plot]:
    min_plot_area_sqm = size_sqm * (1 - tolerance)
    max_plot_area_sqm = size_sqm * (1 + tolerance)
    return await search_plots(
        community=area,
        min_plot_area_sqm=min_plot_area_sqm,
        max_plot_area_sqm=max_plot_area_sqm,
        limit=50,
    )


async def search_land_plots(area: str, q: str, limit: int = 30) -> list[Plot]:
    return await search_plots(q=q, community=area, limit=limit)


async def get_comparable_data(project_ids: list[int]) -> ComparableData | None:
    if not project_ids:
        return None

    buildings_sql = """
    SELECT
        count() AS no_of_buildings,
        avg(floors) AS avg_floors
    FROM ch_buildings
    WHERE project_id IN ({project_ids:Array(Int32)})
      AND floors > 0
    """
    buildings_rows = await query(buildings_sql, {"project_ids": project_ids})
    b = buildings_rows[0] if buildings_rows else {}
    no_of_buildings = int(b.get("no_of_buildings") or 0)
    avg_floors = float(b["avg_floors"]) if b.get("avg_floors") else None

    project_sql = """
    SELECT project_id, project_name_en, area_name_en
    FROM ch_projects
    WHERE project_id IN ({project_ids:Array(Int32)})
    """
    project_rows = await query(project_sql, {"project_ids": project_ids})
    project_names = [r["project_name_en"] for r in project_rows if r.get("project_name_en")]
    area_names = [r["area_name_en"] for r in project_rows if r.get("area_name_en")]

    canonical_unit_sql = canonical_unit_type_case_sql("rooms_en")
    units_sql = f"""
    SELECT
        {canonical_unit_sql} AS unit_type,
        count() AS cnt,
        round(avg(actual_area), 2) AS avg_size_sqm
    FROM ch_units
    WHERE project_id IN ({{project_ids:Array(Int32)}})
      AND actual_area > 0
    GROUP BY unit_type
    HAVING unit_type != 'other'
    ORDER BY cnt DESC
    """
    units_rows = await query(units_sql, {"project_ids": project_ids})
    total_units = sum(r["cnt"] for r in units_rows)

    price_sql = f"""
    SELECT
        {canonical_unit_sql} AS unit_type,
        round(median(meter_sale_price), 0) AS median_price_sqm
    FROM ch_transactions
    WHERE project_name_en IN ({{project_names:Array(String)}})
      AND meter_sale_price > 0
      AND instance_date >= today() - 730
    GROUP BY unit_type
    HAVING unit_type != 'other'
    """
    price_rows = await query(price_sql, {"project_names": project_names}) if project_names else []
    price_by_type = {r["unit_type"]: float(r["median_price_sqm"]) for r in price_rows}

    unit_mix = [
        UnitTypeData(
            type=str(r["unit_type"]),
            count=int(r["cnt"]),
            percentage=round((r["cnt"] / total_units) * 100, 1) if total_units else 0,
            avg_size_sqm=float(r["avg_size_sqm"]),
            avg_price_sqm=price_by_type.get(r["unit_type"]),
        )
        for r in units_rows
    ]

    return ComparableData(
        project_id=project_ids[0],
        project_name=", ".join(project_names[:3]) or f"Project {project_ids[0]}",
        area_name=area_names[0] if area_names else "Unknown",
        no_of_buildings=no_of_buildings,
        avg_floors=avg_floors,
        unit_mix=unit_mix,
        price_per_sqm_by_type=price_by_type,
    )
