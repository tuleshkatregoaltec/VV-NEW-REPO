from __future__ import annotations

from app.area.models import (
    AreaDetailResponse,
    AreaDeveloperExposure,
    AreaListItem,
    AreaListResponse,
    AreaProjectSnapshot,
)
from app.clickhouse.client import query

_SORT_OPTIONS = {
    "units": "pipeline_units DESC, active_projects DESC, area_name_en ASC",
    "volume": "total_sales_volume_12m DESC, pipeline_units DESC, area_name_en ASC",
    "transactions": "sales_transaction_count_12m DESC, pipeline_units DESC, area_name_en ASC",
    "yield": "gross_yield_pct DESC NULLS LAST, pipeline_units DESC, area_name_en ASC",
    "completion": "avg_completion_pct DESC NULLS LAST, pipeline_units DESC, area_name_en ASC",
    "developers": "active_developers DESC, pipeline_units DESC, area_name_en ASC",
}

_AREA_MATCH_SQL = """
    replaceRegexpAll(lowerUTF8(trimBoth(ifNull(area_name_en, ''))), '[\\s\\-\\(\\)\\.,]+', '')
    = replaceRegexpAll(lowerUTF8(trimBoth(ifNull({area_name:String}, ''))), '[\\s\\-\\(\\)\\.,]+', '')
"""


def _resolve_sort_by(sort_by: str) -> str:
    return _SORT_OPTIONS.get(sort_by, _SORT_OPTIONS["units"])


async def list_areas(
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "units",
    search: str | None = None,
) -> AreaListResponse:
    order_by_sql = _resolve_sort_by(sort_by)
    where_clauses = ["area_name_en != ''"]
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if search and search.strip():
        where_clauses.append(
            "positionCaseInsensitive(coalesce(area_name_en, ''), {search:String}) > 0"
        )
        params["search"] = search.strip()
    where_sql = " AND ".join(where_clauses)
    rows = await query(
        f"""
        SELECT
            area_name_en,
            area_id,
            active_projects,
            completed_projects,
            overdue_projects,
            pipeline_units,
            units_delivering_next_12_months,
            active_developers,
            avg_completion_pct,
            avg_delivery_confidence,
            sales_transaction_count_12m,
            rental_contract_count_12m,
            total_sales_volume_12m,
            median_sale_price,
            median_annual_rent,
            avg_sale_price_sqm_12m,
            avg_rent_price_sqm_12m,
            gross_yield_pct,
            top_developers
        FROM ch_area_fact
        WHERE {where_sql}
        ORDER BY {order_by_sql}
        LIMIT {{limit:Int32}} OFFSET {{offset:Int32}}
        """,
        params,
    )
    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total_result = await query(
        f"""
        SELECT count() AS total
        FROM ch_area_fact
        WHERE {where_sql}
        """,
        count_params,
    )

    return AreaListResponse(
        areas=[
            AreaListItem(
                area_name=row["area_name_en"],
                area_id=row.get("area_id"),
                active_projects=row.get("active_projects", 0),
                completed_projects=row.get("completed_projects", 0),
                overdue_projects=row.get("overdue_projects", 0),
                pipeline_units=row.get("pipeline_units", 0),
                units_delivering_next_12_months=row.get("units_delivering_next_12_months", 0),
                active_developers=row.get("active_developers", 0),
                avg_completion_pct=row.get("avg_completion_pct"),
                avg_delivery_confidence=row.get("avg_delivery_confidence"),
                sales_transaction_count_12m=row.get("sales_transaction_count_12m", 0),
                rental_contract_count_12m=row.get("rental_contract_count_12m", 0),
                total_sales_volume_12m=float(row.get("total_sales_volume_12m") or 0),
                median_sale_price=row.get("median_sale_price"),
                median_annual_rent=row.get("median_annual_rent"),
                avg_sale_price_sqm_12m=row.get("avg_sale_price_sqm_12m"),
                avg_rent_price_sqm_12m=row.get("avg_rent_price_sqm_12m"),
                gross_yield_pct=row.get("gross_yield_pct"),
                top_developers=list(row.get("top_developers") or []),
            )
            for row in rows
        ],
        total=total_result[0]["total"] if total_result else 0,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
    )


async def get_area_detail(area_name: str) -> AreaDetailResponse:
    detail_rows = await query(
        f"""
        SELECT
            area_name_en,
            area_id,
            active_projects,
            completed_projects,
            overdue_projects,
            pipeline_units,
            units_delivering_next_12_months,
            active_developers,
            avg_completion_pct,
            avg_delivery_confidence,
            sales_transaction_count_12m,
            rental_contract_count_12m,
            total_sales_volume_12m,
            median_sale_price,
            median_annual_rent,
            avg_sale_price_sqm_12m,
            avg_rent_price_sqm_12m,
            gross_yield_pct,
            top_developers,
            top_master_projects
        FROM ch_area_fact
        WHERE {_AREA_MATCH_SQL}
        LIMIT 1
        """,
        {"area_name": area_name},
    )
    if not detail_rows:
        raise ValueError("Area not found")

    developer_rows = await query(
        f"""
        SELECT
            developer_name,
            count() AS project_count,
            sum(no_of_units) AS pipeline_units,
            round(sum(total_sales_volume_12m), 2) AS total_sales_volume_12m,
            round(avgIf(percent_completed, percent_completed IS NOT NULL), 2) AS avg_completion_pct
        FROM ch_project_fact
        WHERE {_AREA_MATCH_SQL}
          AND developer_name != ''
        GROUP BY developer_name
        ORDER BY pipeline_units DESC, total_sales_volume_12m DESC, developer_name ASC
        LIMIT 8
        """,
        {"area_name": area_name},
    )

    project_rows = await query(
        f"""
        SELECT
            project_id,
            project_name_en,
            developer_name,
            master_project_en,
            completion_status,
            pipeline_status,
            no_of_units,
            percent_completed,
            estimated_delivery_confidence,
            total_sales_volume_12m,
            median_sale_price,
            median_annual_rent,
            gross_yield_pct
        FROM ch_project_fact
        WHERE {_AREA_MATCH_SQL}
        ORDER BY total_sales_volume_12m DESC, no_of_units DESC, project_name_en ASC
        LIMIT 12
        """,
        {"area_name": area_name},
    )

    detail = detail_rows[0]
    return AreaDetailResponse(
        area_name=detail["area_name_en"],
        area_id=detail.get("area_id"),
        active_projects=detail.get("active_projects", 0),
        completed_projects=detail.get("completed_projects", 0),
        overdue_projects=detail.get("overdue_projects", 0),
        pipeline_units=detail.get("pipeline_units", 0),
        units_delivering_next_12_months=detail.get("units_delivering_next_12_months", 0),
        active_developers=detail.get("active_developers", 0),
        avg_completion_pct=detail.get("avg_completion_pct"),
        avg_delivery_confidence=detail.get("avg_delivery_confidence"),
        sales_transaction_count_12m=detail.get("sales_transaction_count_12m", 0),
        rental_contract_count_12m=detail.get("rental_contract_count_12m", 0),
        total_sales_volume_12m=float(detail.get("total_sales_volume_12m") or 0),
        median_sale_price=detail.get("median_sale_price"),
        median_annual_rent=detail.get("median_annual_rent"),
        avg_sale_price_sqm_12m=detail.get("avg_sale_price_sqm_12m"),
        avg_rent_price_sqm_12m=detail.get("avg_rent_price_sqm_12m"),
        gross_yield_pct=detail.get("gross_yield_pct"),
        top_developers=list(detail.get("top_developers") or []),
        top_master_projects=list(detail.get("top_master_projects") or []),
        developer_exposure=[
            AreaDeveloperExposure(
                developer_name=row["developer_name"],
                project_count=row.get("project_count", 0),
                pipeline_units=row.get("pipeline_units", 0),
                total_sales_volume_12m=float(row.get("total_sales_volume_12m") or 0),
                avg_completion_pct=row.get("avg_completion_pct"),
            )
            for row in developer_rows
        ],
        projects=[
            AreaProjectSnapshot(
                project_id=row["project_id"],
                project_name=row.get("project_name_en") or f"Project {row['project_id']}",
                developer_name=row.get("developer_name") or None,
                master_project_en=row.get("master_project_en") or None,
                completion_status=row.get("completion_status") or "planned",
                pipeline_status=row.get("pipeline_status") or "unscheduled",
                no_of_units=row.get("no_of_units", 0),
                percent_completed=row.get("percent_completed"),
                estimated_delivery_confidence=float(row.get("estimated_delivery_confidence") or 0),
                total_sales_volume_12m=float(row.get("total_sales_volume_12m") or 0),
                median_sale_price=row.get("median_sale_price"),
                median_annual_rent=row.get("median_annual_rent"),
                gross_yield_pct=row.get("gross_yield_pct"),
            )
            for row in project_rows
        ],
    )
