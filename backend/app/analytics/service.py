"""Business logic for project analytics — merges parallel ClickHouse results."""

import asyncio
import math
import re
from datetime import date, timedelta
from typing import Literal, Optional

from app.analytics.models import (
    AnalyticsUnitComposition,
    PriceDistributionBucket,
    ProjectAnalyticsResponse,
    ProjectConfigurationRow,
    ProjectForecastPoint,
    ProjectForecastResponse,
    ProjectMeta,
    ProjectPipelinePoint,
    ProjectPipelineResponse,
    ProjectPriceDistributionResponse,
    ProjectRentalSummary,
    ProjectSalesSummary,
    ProjectSearchItem,
    ProjectSearchResponse,
    ProjectTrendPoint,
    ProjectTrendsResponse,
    PropertyTypeBreakdown,
    RegTypeBreakdown,
    RoomAnalytics,
    SubProjectItem,
    SubProjectsResponse,
)
from app.analytics.queries import (
    ProjectFilterType,
    ProjectScopeType,
    TrendInterval,
    area_supply_projects,
    project_configuration_sales,
    project_developers_by_scope,
    project_meta_by_master,
    project_meta_by_name,
    project_meta_by_virtual_master,
    project_offplan_price_curve,
    project_price_distribution,
    project_price_trends,
    project_rentals_by_rooms,
    project_rentals_summary,
    project_sales_by_property_type,
    project_sales_by_reg_type,
    project_sales_by_rooms,
    project_sales_summary,
    project_units_composition,
    search_projects,
    search_sub_projects,
)
from app.clickhouse.client import query

# Room sort order: Studio first, then numeric bedrooms, then anything else
_ROOM_ORDER = {"Studio": 0}
_CONFIG_PRICE_MIN_SAMPLE_SIZE = 3
_CONFIG_MOMENTUM_MIN_SAMPLE_SIZE = 20
_BEDROOM_RE = re.compile(r"^\d+\s+B/R$", re.IGNORECASE)


async def _latest_sales_anchor_date() -> date:
    rows = await query(
        """
        SELECT max(instance_date) AS latest_sales_date
        FROM ch_transactions
        WHERE trans_group_en = 'Sales'
          AND actual_worth > 0
          AND instance_date <= today()
        """,
        {},
    )
    if not rows:
        return date.today()

    value = rows[0].get("latest_sales_date")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return date.today()
    return date.today()


def _room_sort_key(rooms: str) -> tuple:
    if rooms in _ROOM_ORDER:
        return (0, 0)
    # Extract leading number e.g. "1 B/R" → 1
    parts = rooms.split()
    try:
        return (1, int(parts[0]))
    except (ValueError, IndexError):
        return (2, rooms)


def _normalize_label(value: object) -> Optional[str]:
    label = " ".join(str(value).split()) if value is not None else ""
    return label or None


def _unique_normalized_labels(values: list[object]) -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    for value in values:
        label = _normalize_label(value)
        if label is None:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def _is_residential_config_room(rooms: Optional[str]) -> bool:
    label = _normalize_label(rooms)
    if label is None:
        return False

    upper = label.upper()
    if upper in {"NA", "N/A", "NONE", "NULL"}:
        return False
    if upper == "STUDIO":
        return True
    if _BEDROOM_RE.match(label):
        return True
    return "PENTHOUSE" in upper


def _positive_float(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _pct_change(current: object, previous: object) -> Optional[float]:
    current_number = _positive_float(current)
    previous_number = _positive_float(previous)
    if current_number is None or previous_number is None:
        return None
    return round((current_number - previous_number) / previous_number * 100, 1)


def _sampled_count_pct_change(current: int, previous: int) -> Optional[float]:
    if current < _CONFIG_MOMENTUM_MIN_SAMPLE_SIZE or previous < _CONFIG_MOMENTUM_MIN_SAMPLE_SIZE:
        return None
    denominator = (current + previous) / 2
    if denominator <= 0:
        return None
    return round((current - previous) / denominator * 100, 1)


def _coalesce_delivery_date(row: dict) -> Optional[date]:
    return row.get("completion_date") or row.get("project_end_date")


def _quarter_start(dt: date) -> date:
    month = ((dt.month - 1) // 3) * 3 + 1
    return date(dt.year, month, 1)


def _add_months(dt: date, months: int) -> date:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    return date(year, month, 1)


async def get_project_search(search: str, limit: int = 50) -> ProjectSearchResponse:
    """Return matching projects for the dropdown selector."""
    pattern = f"%{search.lower()}%" if search.strip() else "%"
    rows = await query(
        search_projects(),
        {"search_pattern": pattern, "limit": limit},
    )
    return ProjectSearchResponse(
        projects=[ProjectSearchItem(name=r["name"], filter_type=r["filter_type"]) for r in rows]
    )


async def get_sub_project_list(
    master_project: str, filter_type: ProjectFilterType = "master"
) -> SubProjectsResponse:
    """Return sub-projects for a given master/virtual_master, sorted by transaction volume."""
    param = master_project + " - %" if filter_type == "virtual_master" else master_project
    rows = await query(
        search_sub_projects(filter_type),
        {"master_project": param},
    )
    return SubProjectsResponse(
        sub_projects=[
            SubProjectItem(name=r["project_name_en"], transaction_count=int(r["transaction_count"]))
            for r in rows
        ]
    )


async def _get_market_summary(project_name: str) -> ProjectAnalyticsResponse:
    """Return a quick citywide summary from the local materialized fact table.

    The detailed analytics queries intentionally retain their raw, unit-level
    paths for a selected project.  Running all of those citywide at once is
    prohibitively expensive on a local ClickHouse instance, so the landing
    scope uses the already materialized 12-month project aggregates instead.
    """
    rows = await query(
        """
        SELECT
            sum(pf.sales_transaction_count_12m) AS sales_count,
            sum(pf.total_sales_volume_12m) AS sales_volume,
            if(
                sum(pf.sales_transaction_count_12m) > 0,
                sum(pf.median_sale_price * pf.sales_transaction_count_12m)
                    / sum(pf.sales_transaction_count_12m),
                0
            ) AS avg_sale_price,
            avgOrNull(pf.avg_sale_price_sqm_12m) AS avg_sale_price_sqm,
            median(pf.median_sale_price) AS median_sale_price,
            sum(pf.rental_contract_count_12m) AS rental_count,
            sum(pf.median_annual_rent * pf.rental_contract_count_12m) AS rental_value,
            median(pf.median_annual_rent) AS median_annual_rent,
            avgOrNull(pf.avg_rent_price_sqm_12m) AS median_rent_sqm,
            median(pf.gross_yield_pct) AS gross_yield_pct,
            sum(pf.no_of_units) AS unit_count
        FROM ch_project_fact AS pf
        """,
        {},
    )
    row = rows[0] if rows else {}
    sales_count = int(row.get("sales_count") or 0)
    rental_count = int(row.get("rental_count") or 0)
    median_sale_price = float(row.get("median_sale_price") or 0)
    median_annual_rent = float(row.get("median_annual_rent") or 0)
    yield_pct = _positive_float(row.get("gross_yield_pct"))
    if yield_pct is not None:
        yield_pct = round(yield_pct, 2)

    return ProjectAnalyticsResponse(
        project=ProjectMeta(
            project_name=project_name,
            area_name="Dubai",
            developer_name="All developers",
            no_of_units=int(row.get("unit_count") or 0) or None,
        ),
        sales=ProjectSalesSummary(
            transaction_count=sales_count,
            total_volume=float(row.get("sales_volume") or 0),
            avg_price=float(row.get("avg_sale_price") or 0),
            avg_price_sqm=float(row.get("avg_sale_price_sqm") or 0),
            median_price=median_sale_price,
        ),
        rentals=ProjectRentalSummary(
            contract_count=rental_count,
            total_annual_value=float(row.get("rental_value") or 0),
            median_annual_rent=median_annual_rent,
            median_rent_sqm=float(row.get("median_rent_sqm") or 0),
        ),
        overall_gross_yield_pct=yield_pct,
        by_rooms=[],
        by_property_type=[],
        by_reg_type=[],
        unit_composition=[],
        configuration_analysis=[],
    )


async def get_project_summary(
    project_name: str,
    filter_type: ProjectScopeType = "project",
    master_project: Optional[str] = None,
) -> ProjectAnalyticsResponse:
    """
    Run ClickHouse queries in parallel and merge into a single response.
    filter_type controls the WHERE clause: 'master', 'virtual_master', 'project', or 'market'.
    For virtual_master, project_name is used as a LIKE prefix (suffix ' - %' appended here).
    """
    if filter_type == "market":
        return await _get_market_summary(project_name)

    # For LIKE queries the param needs the wildcard appended
    like_name = project_name + " - %" if filter_type == "virtual_master" else project_name
    params = {} if filter_type == "market" else {"project_name": like_name}

    # Unit composition: master/project use master_project_en equality;
    # virtual_master uses project_name_en LIKE (ch_units also lacks master_project_en for orphans)
    if filter_type == "market":
        units_params = {}
    elif filter_type == "virtual_master":
        units_params = {"project_name": like_name}
    elif filter_type == "master":
        units_params = {"project_name": project_name}
    else:
        units_params = {"project_name": master_project or project_name}

    if filter_type == "market":
        meta_task = asyncio.sleep(0, result=[])
    else:
        meta_fn = {
            "master": project_meta_by_master,
            "virtual_master": project_meta_by_virtual_master,
            "project": project_meta_by_name,
        }[filter_type]
        # meta for master/virtual_master uses the like_name for virtual (LIKE) or plain name
        meta_params = (
            {"project_name": like_name}
            if filter_type == "virtual_master"
            else {"project_name": project_name}
        )
        meta_task = query(meta_fn(), meta_params)

    if filter_type in ("master", "virtual_master"):
        developer_task = query(project_developers_by_scope(filter_type), meta_params)
    else:
        developer_task = asyncio.sleep(0, result=[])

    existing_params = {**params, "reg_type_en": "Existing Properties"}
    offplan_params = {**params, "reg_type_en": "Off-Plan Properties"}

    # project_rentals_by_rooms uses {project_name} for both rent and units filters
    rent_rooms_params = params

    (
        sales_sum_rows,
        sales_sum_existing_rows,
        sales_rooms_rows,
        sales_rooms_existing_rows,
        config_all_rows,
        config_offplan_rows,
        config_secondary_rows,
        sales_type_rows,
        sales_reg_rows,
        rent_sum_rows,
        rent_rooms_rows,
        units_rows,
        meta_rows,
        developer_rows,
    ) = await asyncio.gather(
        query(project_sales_summary(filter_type), params),
        query(
            project_sales_summary(filter_type, reg_type="Existing Properties"),
            existing_params,
        ),
        query(project_sales_by_rooms(filter_type), params),
        query(
            project_sales_by_rooms(filter_type, reg_type="Existing Properties"),
            existing_params,
        ),
        query(project_configuration_sales(filter_type), params),
        query(
            project_configuration_sales(filter_type, reg_type="Off-Plan Properties"),
            offplan_params,
        ),
        query(
            project_configuration_sales(filter_type, reg_type="Existing Properties"),
            existing_params,
        ),
        query(project_sales_by_property_type(filter_type), params),
        query(project_sales_by_reg_type(filter_type), params),
        query(project_rentals_summary(filter_type), params),
        query(project_rentals_by_rooms(filter_type), rent_rooms_params),
        query(project_units_composition(filter_type), units_params),
        meta_task,
        developer_task,
    )

    # --- Project metadata ---
    project: Optional[ProjectMeta] = None
    if filter_type == "market":
        project = ProjectMeta(
            project_name=project_name,
            area_name="Dubai",
            developer_name="All developers",
        )
    elif meta_rows:
        m = meta_rows[0]
        if filter_type in ("master", "virtual_master"):
            raw_devs = m.get("developer_names") or []
            developer_names = _unique_normalized_labels(
                [row.get("developer_name_en") for row in developer_rows]
            )
            if not developer_names:
                developer_names = _unique_normalized_labels(raw_devs) if raw_devs else []
            top_developer = _normalize_label(m.get("developer_name_en"))
            if not developer_names and top_developer:
                developer_names = [top_developer, *developer_names]
            project = ProjectMeta(
                project_name=project_name,
                area_name=m.get("area_name_en") or None,
                developer_name=developer_names[0] if developer_names else top_developer,
                developer_names=developer_names,
                project_status=m.get("project_status") or None,
                completion_date=m.get("completion_date") or None,
                percent_completed=float(m["percent_completed"])
                if m.get("percent_completed") is not None
                else None,
                no_of_units=int(m["no_of_units"]) if m.get("no_of_units") is not None else None,
                no_of_buildings=int(m["no_of_buildings"])
                if m.get("no_of_buildings") is not None
                else None,
            )
        else:
            project = ProjectMeta(
                project_name=m.get("project_name_en", project_name),
                area_name=m.get("area_name_en") or None,
                developer_name=_normalize_label(m.get("developer_name_en")),
                project_status=m.get("project_status") or None,
                completion_date=m.get("completion_date") or None,
                percent_completed=float(m["percent_completed"])
                if m.get("percent_completed") is not None
                else None,
                no_of_units=int(m["no_of_units"]) if m.get("no_of_units") is not None else None,
                no_of_buildings=int(m["no_of_buildings"])
                if m.get("no_of_buildings") is not None
                else None,
            )

    # --- Sales summary ---
    s = sales_sum_rows[0] if sales_sum_rows else {}
    sales = ProjectSalesSummary(
        transaction_count=int(s.get("transaction_count", 0)),
        total_volume=float(s.get("total_volume", 0) or 0),
        avg_price=float(s.get("avg_price", 0) or 0),
        avg_price_sqm=float(s.get("avg_price_sqm", 0) or 0),
        median_price=float(s.get("median_price", 0) or 0),
    )

    # --- Rental summary ---
    r = rent_sum_rows[0] if rent_sum_rows else {}
    rentals = ProjectRentalSummary(
        contract_count=int(r.get("contract_count", 0)),
        total_annual_value=float(r.get("total_annual_value", 0) or 0),
        median_annual_rent=float(r.get("median_annual_rent", 0) or 0),
        median_rent_sqm=float(r.get("median_rent_sqm", 0) or 0),
    )

    # --- Overall gross yield ---
    # Use existing-only median_price as denominator — off-plan launch prices are discounted
    # and would produce artificially inflated yields (e.g. JVC showing ~25%).
    # Median/median: both sides use the same central tendency measure for a consistent yield.
    existing_median_price = float(
        (sales_sum_existing_rows[0].get("median_price") or 0) if sales_sum_existing_rows else 0
    )
    overall_yield: Optional[float] = None
    if existing_median_price > 0 and rentals.median_annual_rent > 0:
        overall_yield = round(rentals.median_annual_rent / existing_median_price * 100, 2)

    # --- By rooms (merge sales + rentals) ---
    sales_by_room = {row["rooms_en"]: row for row in sales_rooms_rows}
    # Existing-only prices used as yield denominator — same rationale as overall_gross_yield_pct
    sales_existing_by_room = {row["rooms_en"]: row for row in sales_rooms_existing_rows}
    rent_by_room = {row["rooms_en"]: row for row in rent_rooms_rows}
    all_rooms = set(sales_by_room) | set(rent_by_room)

    by_rooms: list[RoomAnalytics] = []
    for rooms in all_rooms:
        s_row = sales_by_room.get(rooms, {})
        s_ex_row = sales_existing_by_room.get(rooms, {})
        r_row = rent_by_room.get(rooms, {})
        avg_sale = float(s_row.get("avg_sale_price", 0) or 0)
        existing_median_sale = float(s_ex_row.get("median_sale_price", 0) or 0)
        median_rent = float(r_row.get("median_annual_rent", 0) or 0)
        yield_pct: Optional[float] = None
        if existing_median_sale > 0 and median_rent > 0:
            yield_pct = round(median_rent / existing_median_sale * 100, 2)
        by_rooms.append(
            RoomAnalytics(
                rooms=rooms,
                sale_count=int(s_row.get("sale_count", 0)),
                avg_sale_price=avg_sale,
                avg_sale_price_sqm=float(s_row.get("avg_sale_price_sqm", 0) or 0),
                rental_count=int(r_row.get("rental_count", 0)),
                median_annual_rent=median_rent,
                median_rent_sqm=float(r_row.get("median_rent_sqm", 0) or 0),
                gross_yield_pct=yield_pct,
            )
        )
    by_rooms.sort(key=lambda x: _room_sort_key(x.rooms))

    # --- By property type ---
    total_sales = sum(int(row["count"]) for row in sales_type_rows) or 1
    by_property_type = [
        PropertyTypeBreakdown(
            property_type=row["property_type_en"],
            count=int(row["count"]),
            avg_price=float(row["avg_price"] or 0),
            pct_of_total=round(int(row["count"]) / total_sales * 100, 1),
        )
        for row in sales_type_rows
    ]

    # --- By registration type ---
    total_reg = sum(int(row["count"]) for row in sales_reg_rows) or 1
    by_reg_type = [
        RegTypeBreakdown(
            reg_type=row["reg_type_en"],
            count=int(row["count"]),
            avg_price=float(row["avg_price"] or 0),
            pct_of_total=round(int(row["count"]) / total_reg * 100, 1),
        )
        for row in sales_reg_rows
    ]

    # --- Unit composition ---
    unit_count_total = sum(int(row["unit_count"]) for row in units_rows)
    if filter_type == "market" and project is not None:
        project.no_of_units = unit_count_total if unit_count_total > 0 else None

    total_units = unit_count_total or 1
    unit_composition = [
        AnalyticsUnitComposition(
            rooms=room,
            count=int(row["unit_count"]),
            pct_of_total=round(int(row["unit_count"]) / total_units * 100, 1),
            avg_unit_size_sqm=float(row.get("avg_unit_size_sqm", 0) or 0),
        )
        for row in units_rows
        if (room := _normalize_label(row.get("rooms_en"))) is not None
    ]
    unit_composition.sort(key=lambda x: _room_sort_key(x.rooms))

    unit_rows_by_room = {
        room: row
        for row in units_rows
        if (room := _normalize_label(row.get("rooms_en"))) is not None
    }

    def _build_configuration_rows(
        segment: Literal["all", "off_plan", "secondary"], sales_rows: list[dict]
    ) -> list[ProjectConfigurationRow]:
        sales_lookup = {
            room: row
            for row in sales_rows
            if (room := _normalize_label(row.get("rooms_en"))) is not None
        }
        room_keys = {
            room
            for room in set(unit_rows_by_room) | set(sales_lookup)
            if _is_residential_config_room(room)
        }
        rows: list[ProjectConfigurationRow] = []

        for rooms in room_keys:
            sale_row = sales_lookup.get(rooms, {})
            unit_row = unit_rows_by_room.get(rooms, {})
            rent_row = rent_by_room.get(rooms, {}) if segment != "off_plan" else {}

            stock_units = int(unit_row.get("unit_count", 0) or 0)
            sales_last_12m = int(sale_row.get("sales_last_12m", 0) or 0)
            sales_prev_12m = int(sale_row.get("sales_prev_12m", 0) or 0)
            sales_last_90d = int(sale_row.get("sales_last_90d", 0) or 0)
            sales_prev_90d = int(sale_row.get("sales_prev_90d", 0) or 0)
            sale_count = int(sale_row.get("sale_count", 0) or 0)
            median_sale_price = float(sale_row.get("median_sale_price", 0) or 0)
            median_annual_rent = float(rent_row.get("median_annual_rent", 0) or 0)

            if (
                stock_units <= 0
                and sale_count <= 0
                and int(rent_row.get("rental_count", 0) or 0) <= 0
            ):
                continue
            if sales_last_12m < _CONFIG_PRICE_MIN_SAMPLE_SIZE:
                continue

            gross_yield_pct: Optional[float] = None
            if segment != "off_plan" and median_sale_price > 0 and median_annual_rent > 0:
                gross_yield_pct = round(median_annual_rent / median_sale_price * 100, 2)

            absorption_rate_pct: Optional[float] = None
            if stock_units > 0:
                absorption_rate_pct = round(sales_last_12m / stock_units * 100, 1)

            rows.append(
                ProjectConfigurationRow(
                    market_segment=segment,
                    rooms=rooms,
                    stock_units=stock_units,
                    sale_count=sale_count,
                    sales_last_12m=sales_last_12m,
                    avg_sale_price=float(sale_row.get("avg_sale_price", 0) or 0),
                    median_sale_price=median_sale_price,
                    avg_sale_price_sqm=float(sale_row.get("avg_sale_price_sqm", 0) or 0),
                    avg_unit_size_sqm=float(unit_row.get("avg_unit_size_sqm", 0) or 0),
                    rental_count=int(rent_row.get("rental_count", 0) or 0),
                    median_annual_rent=median_annual_rent,
                    median_rent_sqm=float(rent_row.get("median_rent_sqm", 0) or 0),
                    gross_yield_pct=gross_yield_pct,
                    price_change_yoy_pct=_pct_change(
                        sale_row.get("avg_price_sqm_last_12m"),
                        sale_row.get("avg_price_sqm_prev_12m"),
                    )
                    if sales_last_12m >= _CONFIG_PRICE_MIN_SAMPLE_SIZE
                    and sales_prev_12m >= _CONFIG_PRICE_MIN_SAMPLE_SIZE
                    else None,
                    sales_momentum_pct=_sampled_count_pct_change(sales_last_90d, sales_prev_90d),
                    absorption_rate_pct=absorption_rate_pct,
                    price_p25=float(sale_row.get("price_p25", 0) or 0),
                    price_p50=float(sale_row.get("price_p50", 0) or 0),
                    price_p75=float(sale_row.get("price_p75", 0) or 0),
                )
            )

        rows.sort(key=lambda x: _room_sort_key(x.rooms))
        return rows

    configuration_analysis = [
        *_build_configuration_rows("all", config_all_rows),
        *_build_configuration_rows("off_plan", config_offplan_rows),
        *_build_configuration_rows("secondary", config_secondary_rows),
    ]

    return ProjectAnalyticsResponse(
        project=project,
        sales=sales,
        rentals=rentals,
        overall_gross_yield_pct=overall_yield,
        by_rooms=by_rooms,
        by_property_type=by_property_type,
        by_reg_type=by_reg_type,
        unit_composition=unit_composition,
        configuration_analysis=configuration_analysis,
    )


async def get_project_trends(
    project_name: str, days: int, filter_type: ProjectScopeType = "project"
) -> ProjectTrendsResponse:
    """Price trend time series for a project over the given number of days."""
    end_dt = date.today()
    start_dt = end_dt - timedelta(days=days)
    interval = _trend_interval_for_days(days)

    like_name = project_name + " - %" if filter_type == "virtual_master" else project_name
    params = {
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
    }
    if filter_type != "market":
        params["project_name"] = like_name

    rows = await query(
        project_price_trends(interval, filter_type),
        params,
    )

    data = [
        ProjectTrendPoint(
            date=row["period"],
            transaction_count=int(row["transaction_count"]),
            avg_price=float(row["avg_price"] or 0),
            avg_price_sqm=float(row["avg_price_sqm"] or 0),
        )
        for row in rows
    ]
    return ProjectTrendsResponse(data=data)


async def get_project_forecast(
    project_name: str, days: int, filter_type: ProjectScopeType = "project"
) -> ProjectForecastResponse:
    """Build a project-level forward price path from historical trend and off-plan curve data."""
    if filter_type == "market":
        return ProjectForecastResponse(
            data=[],
            methodology="Citywide Dubai forecasts are not generated from project delivery curves.",
        )

    end_dt = date.today()
    start_dt = end_dt - timedelta(days=days)
    interval = _trend_interval_for_days(days)

    like_name = project_name + " - %" if filter_type == "virtual_master" else project_name
    params = {
        "project_name": like_name,
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
    }
    trend_rows, offplan_rows = await asyncio.gather(
        query(project_price_trends(interval, filter_type), params),
        query(project_offplan_price_curve(interval, filter_type), params),
    )

    historical = [
        ProjectForecastPoint(
            date=row["period"],
            avg_price=float(row["avg_price"] or 0),
            avg_price_sqm=float(row["avg_price_sqm"] or 0),
            series="historical",
        )
        for row in trend_rows
        if float(row.get("avg_price") or 0) > 0
    ]

    summary = await get_project_summary(project_name=project_name, filter_type=filter_type)
    delivery_date = summary.project.completion_date if summary.project else None

    if not historical:
        historical = [
            ProjectForecastPoint(
                date=row["period"],
                avg_price=float(row["avg_price"] or 0),
                avg_price_sqm=float(row["avg_price_sqm"] or 0),
                series="historical",
            )
            for row in offplan_rows
            if float(row.get("avg_price") or 0) > 0
        ]

    if not historical:
        return ProjectForecastResponse(
            data=[],
            delivery_date=delivery_date,
            methodology="No residential sales history was available to construct a project-level forecast.",
        )

    monthly_growth_rates: list[float] = []
    for prev, curr in zip(historical, historical[1:]):
        prev_price = float(prev.avg_price_sqm or 0)
        curr_price = float(curr.avg_price_sqm or 0)
        if prev_price > 0 and curr_price > 0:
            monthly_growth_rates.append((curr_price / prev_price) - 1)

    delivery_curve_rates: list[float] = []
    for prev, curr in zip(offplan_rows, offplan_rows[1:]):
        prev_price = float(prev.get("avg_price_sqm") or 0)
        curr_price = float(curr.get("avg_price_sqm") or 0)
        prev_months = float(prev.get("avg_months_to_delivery") or 0)
        curr_months = float(curr.get("avg_months_to_delivery") or 0)
        delivery_step = prev_months - curr_months
        if prev_price > 0 and curr_price > 0 and delivery_step > 0:
            delivery_curve_rates.append(((curr_price / prev_price) - 1) / delivery_step)

    recent_growth = (
        sum(monthly_growth_rates[-3:]) / len(monthly_growth_rates[-3:])
        if monthly_growth_rates[-3:]
        else 0.0
    )
    delivery_curve = (
        sum(delivery_curve_rates[-4:]) / len(delivery_curve_rates[-4:])
        if delivery_curve_rates[-4:]
        else 0.0
    )
    monthly_growth = max(-0.01, min(0.018, recent_growth * 0.7 + delivery_curve * 0.3))

    last_point = historical[-1]
    forecast_points: list[ProjectForecastPoint] = []
    if delivery_date and delivery_date > last_point.date:
        horizon_months = max(
            1,
            min(
                12,
                (delivery_date.year - last_point.date.year) * 12
                + (delivery_date.month - last_point.date.month),
            ),
        )
    else:
        horizon_months = 6

    next_date = _add_months(last_point.date, 1)
    next_price = last_point.avg_price
    next_price_sqm = last_point.avg_price_sqm

    for _ in range(horizon_months):
        next_price *= 1 + monthly_growth
        next_price_sqm *= 1 + monthly_growth
        forecast_points.append(
            ProjectForecastPoint(
                date=next_date,
                avg_price=round(next_price, 2),
                avg_price_sqm=round(next_price_sqm, 2),
                series="forecast",
            )
        )
        next_date = _add_months(next_date, 1)

    return ProjectForecastResponse(
        data=[*historical, *forecast_points],
        delivery_date=delivery_date,
        methodology=(
            "Forecast extends the recorded residential project trend, then blends recent "
            "price/sqm movement with the off-plan delivery curve where delivery-dated launches exist."
        ),
    )


async def get_project_pipeline(
    project_name: str, filter_type: ProjectScopeType = "project"
) -> ProjectPipelineResponse:
    """Area-level delivery pipeline grouped by quarter around the selected project."""
    if filter_type == "market":
        area_name = "Dubai"
        developer_name = None
        rows = await query(area_supply_projects(filter_by_area=False), {})
    else:
        summary = await get_project_summary(project_name=project_name, filter_type=filter_type)
        area_name = summary.project.area_name if summary.project else None
        developer_name = summary.project.developer_name if summary.project else None

        if not area_name:
            return ProjectPipelineResponse(area_name=None, developer_name=developer_name, data=[])

        rows = await query(area_supply_projects(), {"area_name": area_name})

    if not rows:
        return ProjectPipelineResponse(area_name=area_name, developer_name=developer_name, data=[])

    today = await _latest_sales_anchor_date()
    start_quarter = _quarter_start(date(today.year - 1, 1, 1))
    periods = [_add_months(start_quarter, quarter_index * 3) for quarter_index in range(16)]

    completed_by_quarter: dict[date, int] = {}
    pipeline_by_quarter: dict[date, int] = {}

    for row in rows:
        units = int(row.get("no_of_units") or 0)
        if units <= 0:
            continue

        completion_dt = _coalesce_delivery_date(row)
        if completion_dt:
            quarter = _quarter_start(completion_dt)
            if completion_dt <= today:
                completed_by_quarter[quarter] = completed_by_quarter.get(quarter, 0) + units
            else:
                pipeline_by_quarter[quarter] = pipeline_by_quarter.get(quarter, 0) + units

    cumulative_existing = sum(units for q, units in completed_by_quarter.items() if q < periods[0])
    cumulative_future = 0

    data: list[ProjectPipelinePoint] = []
    today_quarter = _quarter_start(today)
    for period in periods:
        new_pipeline_units = pipeline_by_quarter.get(period, 0)
        if period <= today_quarter:
            cumulative_existing += completed_by_quarter.get(period, 0)
            data.append(
                ProjectPipelinePoint(
                    period=period,
                    existing_stock_units=cumulative_existing,
                    carried_stock_units=0,
                    new_pipeline_units=new_pipeline_units if period == today_quarter else 0,
                )
            )
            continue

        carried_stock_units = cumulative_existing + cumulative_future
        cumulative_future += new_pipeline_units
        data.append(
            ProjectPipelinePoint(
                period=period,
                existing_stock_units=0,
                carried_stock_units=carried_stock_units,
                new_pipeline_units=new_pipeline_units,
            )
        )

    return ProjectPipelineResponse(
        area_name=area_name,
        developer_name=developer_name,
        data=data,
    )


async def get_project_price_distribution(
    project_name: str,
    filter_type: ProjectScopeType = "project",
    reg_type: Optional[str] = None,
) -> ProjectPriceDistributionResponse:
    """Price distribution statistics per bedroom type for bell-curve style visualisation."""
    like_name = project_name + " - %" if filter_type == "virtual_master" else project_name
    params: dict = {} if filter_type == "market" else {"project_name": like_name}
    if reg_type:
        params["reg_type_en"] = reg_type

    rows = await query(project_price_distribution(filter_type, reg_type), params)

    all_bucket: Optional[PriceDistributionBucket] = None
    by_rooms: list[PriceDistributionBucket] = []

    for row in rows:
        bucket = PriceDistributionBucket(
            rooms=row["rooms_en"],
            sale_count=int(row["sale_count"]),
            mean_price=float(row["mean_price"] or 0),
            std_price=float(row["std_price"] or 0),
            log_mean_price=float(row["log_mean_price"] or 0),
            log_std_price=float(row["log_std_price"] or 0),
            p05_price=float(row["p05_price"] or 0),
            p25_price=float(row["p25_price"] or 0),
            p50_price=float(row["p50_price"] or 0),
            p75_price=float(row["p75_price"] or 0),
            p95_price=float(row["p95_price"] or 0),
            mean_price_sqm=float(row["mean_price_sqm"] or 0),
            std_price_sqm=float(row["std_price_sqm"] or 0),
        )
        if row["rooms_en"] == "__all__":
            all_bucket = bucket
        else:
            by_rooms.append(bucket)

    by_rooms.sort(key=lambda x: _room_sort_key(x.rooms))
    return ProjectPriceDistributionResponse(all=all_bucket, by_rooms=by_rooms)


def _trend_interval_for_days(days: int) -> TrendInterval:
    if days <= 30:
        return "day"
    if days <= 180:
        return "week"
    return "month"
