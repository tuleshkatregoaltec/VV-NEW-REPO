"""Analytics API endpoints with flexible filtering from daily aggregates."""

import asyncio
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.analytics.models import (
    AnalyticsResponse,
    AnalyticsSummary,
    MarketTrendPoint,
    MarketTrendResponse,
    ProjectAnalyticsResponse,
    ProjectForecastResponse,
    ProjectPipelineResponse,
    ProjectPriceDistributionResponse,
    ProjectSearchResponse,
    ProjectTrendsResponse,
    RentalAnalyticsResponse,
    RentalSummary,
    SubProjectsResponse,
)
from app.analytics.queries import ProjectFilterType, ProjectScopeType
from app.analytics.service import (
    get_project_forecast,
    get_project_pipeline,
    get_project_price_distribution,
    get_project_search,
    get_project_summary,
    get_project_trends,
    get_sub_project_list,
)
from app.clickhouse.client import query
from app.clickhouse.queries import (
    MARKET_FILTERS,
    price_trends,
    rentals_summary,
    sales_summary,
)
from app.core.decorators import cached_endpoint
from app.core.dependencies import AuthContext, require_active_subscription

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _resolve_project_scope(
    *,
    master_project: Optional[str],
    project: Optional[str],
    filter_type: ProjectFilterType,
) -> tuple[str, ProjectScopeType]:
    if project:
        return project, "project"
    if master_project:
        return master_project, filter_type
    return "Dubai", "market"


@router.get("/sales", response_model=AnalyticsResponse)
async def get_sales_analytics(
    context: AuthContext = Depends(require_active_subscription),
    market_type: Optional[str] = Query(
        default=None,
        description=f"Market type (overrides property_usage/property_type). One of: {', '.join(MARKET_FILTERS)}",
    ),
    property_usage: Optional[str] = Query(
        default="Residential",
        description="Residential or Commercial (ignored if market_type set)",
    ),
    timeframe_days: Optional[int] = Query(
        default=None,
        description="Number of days to look back (overrides start_date if provided)",
    ),
    start_date: Optional[date] = Query(
        default=None, description="Explicit start date (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        default=None, description="Explicit end date (YYYY-MM-DD), defaults to today"
    ),
    master_project: Optional[str] = Query(
        default=None, description="Filter by master project name"
    ),
    property_type: Optional[str] = Query(
        default=None, description="Filter by property type (ignored if market_type set)"
    ),
    rooms: Optional[str] = Query(default=None, description="Filter by room count"),
    reg_type: Optional[str] = Query(default=None, description="Filter by registration type"),
    price_bucket: Optional[str] = Query(
        default=None, description="Filter by price bucket (e.g., '1M-2M')"
    ),
    area_bucket: Optional[str] = Query(
        default=None, description="Filter by area bucket (e.g., '1K-2K')"
    ),
):
    """Get sales analytics with flexible filtering and custom date ranges.

    Supports:
    - Custom date ranges (use start_date/end_date or timeframe_days)
    - market_type for taxonomy-correct filtering (recommended)
    - Manual filtering via property_usage + property_type (legacy)

    Examples:
    - Last 30 days: ?timeframe_days=30
    - By market: ?market_type=residential_units&timeframe_days=90
    - Custom range: ?start_date=2024-01-01&end_date=2024-12-31
    """
    from fastapi import HTTPException

    # Resolve market_type into property_usage / property_type / property_usage_in
    resolved_property_usage = property_usage
    resolved_property_type = property_type
    resolved_property_usage_in = None

    if market_type is not None:
        if market_type not in MARKET_FILTERS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid market_type. Valid values: {list(MARKET_FILTERS)}",
            )
        mf = MARKET_FILTERS[market_type]
        resolved_property_usage = mf.get("property_usage_en")
        resolved_property_usage_in = mf.get("property_usage_en__in")
        resolved_property_type = mf.get("property_type_en", property_type)

    # Calculate date range
    if timeframe_days:
        from datetime import timedelta

        end_date = date.today()
        start_date = end_date - timedelta(days=timeframe_days)
    else:
        if not start_date:
            from datetime import timedelta

            start_date = date.today() - timedelta(days=180)  # Default 6 months
        if not end_date:
            end_date = date.today()

    # Execute ClickHouse query
    try:
        sql = sales_summary(
            property_usage=resolved_property_usage,
            property_usage_in=resolved_property_usage_in,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            master_project=master_project,
            property_type=resolved_property_type,
            rooms=rooms,
            reg_type=reg_type,
            price_bucket=price_bucket,
            area_bucket=area_bucket,
        )

        parameters = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        # Add optional parameters
        if resolved_property_usage is not None:
            parameters["property_usage"] = resolved_property_usage
        if master_project:
            parameters["master_project"] = master_project
        if resolved_property_type:
            parameters["property_type"] = resolved_property_type
        if rooms:
            parameters["rooms"] = rooms
        if reg_type:
            parameters["reg_type"] = reg_type
        if price_bucket:
            parameters["price_bucket"] = price_bucket
        if area_bucket:
            parameters["area_bucket"] = area_bucket

        result = await query(sql, parameters)

    except Exception as e:
        # Log error and return empty response instead of crashing
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error executing sales analytics query: {str(e)}")
        result = []

    if not result:
        # Return empty analytics response
        summary = AnalyticsSummary(
            transaction_count=0,
            total_volume=0.0,
            avg_price=0.0,
            avg_price_sqft=0.0,
            min_price=0.0,
            max_price=0.0,
        )
        return AnalyticsResponse(
            timeframe_days=timeframe_days or (end_date - start_date).days,
            property_usage=property_usage,
            summary=summary,
            trends=[],
            by_property_type=[],
            by_rooms=[],
            by_reg_type=[],
            by_master_project=[],
        )

    # Convert result to summary
    row = result[0]
    summary = AnalyticsSummary(
        transaction_count=row["transaction_count"],
        total_volume=float(row["total_volume"]),
        avg_price=float(row["avg_price"]),
        avg_price_sqft=float(row.get("median_price_per_sqm", 0)),  # Use available field
        min_price=float(row.get("median_price", 0)),  # Use median as approximation
        max_price=float(row.get("avg_price", 0)),  # Use avg as approximation
    )

    # For now, return basic response with just summary
    # TODO: Add trends and breakdowns queries
    return AnalyticsResponse(
        timeframe_days=timeframe_days or (end_date - start_date).days,
        property_usage=property_usage,
        summary=summary,
        trends=[],  # TODO: Implement trends query
        by_property_type=[],  # TODO: Implement breakdowns
        by_rooms=[],
        by_reg_type=[],
        by_master_project=[],
    )


@router.get("/rentals", response_model=RentalAnalyticsResponse)
async def get_rental_analytics(
    context: AuthContext = Depends(require_active_subscription),
    property_usage: str = Query(default="Residential", description="Residential or Commercial"),
    timeframe_days: Optional[int] = Query(
        default=None,
        description="Number of days to look back (overrides start_date if provided)",
    ),
    start_date: Optional[date] = Query(
        default=None, description="Explicit start date (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        default=None, description="Explicit end date (YYYY-MM-DD), defaults to today"
    ),
    master_project: Optional[str] = Query(
        default=None, description="Filter by master project name"
    ),
    property_type: Optional[str] = Query(default=None, description="Filter by property type"),
    rent_bucket: Optional[str] = Query(
        default=None, description="Filter by rent bucket (e.g., '100K-200K')"
    ),
    area_bucket: Optional[str] = Query(
        default=None, description="Filter by area bucket (e.g., '1K-2K')"
    ),
):
    """Get rental analytics with flexible filtering and custom date ranges.

    Supports:
    - Custom date ranges (use start_date/end_date or timeframe_days)
    - Multi-dimensional filtering (combine property_type, location, rent ranges)
    - Bucketed filtering (rent ranges, area ranges)

    Examples:
    - Last 90 days: ?timeframe_days=90
    - Custom range: ?start_date=2024-06-01&end_date=2024-08-31
    - Filtered: ?property_usage=Commercial&rent_bucket=200K-500K
    """
    # Calculate date range
    if timeframe_days:
        from datetime import timedelta

        end_date = date.today()
        start_date = end_date - timedelta(days=timeframe_days)
    else:
        if not start_date:
            from datetime import timedelta

            start_date = date.today() - timedelta(days=180)  # Default 6 months
        if not end_date:
            end_date = date.today()

    # Execute ClickHouse query
    sql = rentals_summary(
        property_usage=property_usage,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        master_project=master_project,
        property_type=property_type,
    )

    parameters = {
        "property_usage": property_usage,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    # Add optional parameters
    if master_project:
        parameters["master_project"] = master_project
    if property_type:
        parameters["property_type"] = property_type

    result = await query(sql, parameters)

    if not result:
        # Return empty rental analytics response
        summary = RentalSummary(
            contract_count=0,
            total_annual_value=0.0,
            avg_annual_rent=0.0,
            avg_rent_sqft=0.0,
            min_annual_rent=0.0,
            max_annual_rent=0.0,
        )
        return RentalAnalyticsResponse(
            timeframe_days=timeframe_days or (end_date - start_date).days,
            property_usage=property_usage,
            summary=summary,
            trends=[],
            by_property_type=[],
            by_master_project=[],
        )

    # Convert result to summary
    row = result[0]
    summary = RentalSummary(
        contract_count=row["contract_count"],
        total_annual_value=float(row["total_annual_value"]),
        avg_annual_rent=float(row["avg_rent"]),
        avg_rent_sqft=float(row.get("median_rent_per_sqm", 0)),
        min_annual_rent=float(row.get("median_rent", 0)),  # Use median as approximation
        max_annual_rent=float(row.get("avg_rent", 0)),  # Use avg as approximation
    )

    # For now, return basic response with just summary
    # TODO: Add trends and breakdowns queries
    return RentalAnalyticsResponse(
        timeframe_days=timeframe_days or (end_date - start_date).days,
        property_usage=property_usage,
        summary=summary,
        trends=[],  # TODO: Implement trends query
        by_property_type=[],  # TODO: Implement breakdowns
        by_master_project=[],
    )


@router.get("/market-trend", response_model=MarketTrendResponse)
async def get_market_trend(
    context: AuthContext = Depends(require_active_subscription),
    days: int = Query(default=180, description="Number of days to look back (30, 90, 180, 365)"),
    market_type: Optional[str] = Query(
        default=None,
        description=f"Market type (overrides property_usage). One of: {', '.join(MARKET_FILTERS)}",
    ),
    property_usage: Optional[str] = Query(
        default="Residential",
        description="Residential or Commercial (ignored if market_type set)",
    ),
):
    """Get aggregated price trend data for the market trend chart.

    Returns trend points plus period-over-period change vs the equivalent prior period.
    """
    from fastapi import HTTPException

    # Resolve market_type
    resolved_property_usage = property_usage
    resolved_property_usage_in = None
    resolved_property_type = None

    if market_type is not None:
        if market_type not in MARKET_FILTERS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid market_type. Valid values: {list(MARKET_FILTERS)}",
            )
        mf = MARKET_FILTERS[market_type]
        resolved_property_usage = mf.get("property_usage_en")
        resolved_property_usage_in = mf.get("property_usage_en__in")
        resolved_property_type = mf.get("property_type_en")

    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    prev_end = start_date
    prev_start = prev_end - timedelta(days=days)

    if days <= 30:
        interval = "day"
    elif days <= 180:
        interval = "week"
    else:
        interval = "month"

    trend_sql = price_trends(
        property_usage=resolved_property_usage,
        property_usage_in=resolved_property_usage_in,
        property_type=resolved_property_type,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        interval=interval,
    )
    current_summary_sql = sales_summary(
        property_usage=resolved_property_usage,
        property_usage_in=resolved_property_usage_in,
        property_type=resolved_property_type,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    prev_summary_sql = sales_summary(
        property_usage=resolved_property_usage,
        property_usage_in=resolved_property_usage_in,
        property_type=resolved_property_type,
        start_date=prev_start.isoformat(),
        end_date=prev_end.isoformat(),
    )

    def _trend_params(s: str, e: str) -> dict:
        p: dict = {"start_date": s, "end_date": e}
        if resolved_property_usage is not None:
            p["property_usage"] = resolved_property_usage
        if resolved_property_type is not None:
            p["property_type"] = resolved_property_type
        return p

    try:
        trend_result, current_result, prev_result = await asyncio.gather(
            query(trend_sql, _trend_params(start_date.isoformat(), end_date.isoformat())),
            query(
                current_summary_sql,
                _trend_params(start_date.isoformat(), end_date.isoformat()),
            ),
            query(
                prev_summary_sql,
                _trend_params(prev_start.isoformat(), prev_end.isoformat()),
            ),
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error executing market trend query: {e}")
        return MarketTrendResponse(data=[], total_transactions=0)

    data = [
        MarketTrendPoint(
            date=row["period"],
            transaction_count=int(row["transaction_count"]),
            avg_price=float(row["avg_price"]),
            avg_price_sqm=float(row["avg_price_sqm"]),
        )
        for row in trend_result
    ]

    def pct_change(current: float, previous: float) -> Optional[float]:
        if not previous:
            return None
        return round((current - previous) / previous * 100, 1)

    avg_price_change_pct = None
    avg_price_sqm_change_pct = None
    if current_result and prev_result:
        curr = current_result[0]
        prev = prev_result[0]
        avg_price_change_pct = pct_change(float(curr["avg_price"]), float(prev["avg_price"]))
        avg_price_sqm_change_pct = pct_change(
            float(curr["median_price_per_sqm"]), float(prev["median_price_per_sqm"])
        )

    return MarketTrendResponse(
        data=data,
        total_transactions=sum(p.transaction_count for p in data),
        avg_price_change_pct=avg_price_change_pct,
        avg_price_sqm_change_pct=avg_price_sqm_change_pct,
    )


# =============================================================================
# PROJECT ANALYTICS ENDPOINTS
# =============================================================================


@router.get("/projects", response_model=ProjectSearchResponse)
async def search_projects_endpoint(
    context: AuthContext = Depends(require_active_subscription),
    search: str = Query(default="", description="Master project name search term"),
    limit: int = Query(default=50, description="Max results to return"),
):
    """Search master project names for the selector dropdown."""
    return await get_project_search(search=search, limit=limit)


@router.get("/project/sub-projects", response_model=SubProjectsResponse)
async def get_sub_projects_endpoint(
    context: AuthContext = Depends(require_active_subscription),
    master_project: str = Query(description="Master project name"),
    filter_type: ProjectFilterType = Query(
        default="master", description="Filter type: master or virtual_master"
    ),
):
    """List sub-projects within a master or virtual master, sorted by transaction count."""
    return await get_sub_project_list(master_project=master_project, filter_type=filter_type)


@router.get("/project/summary", response_model=ProjectAnalyticsResponse)
@cached_endpoint(prefix="analytics:project_summary", expire=900)
async def get_project_summary_endpoint(
    context: AuthContext = Depends(require_active_subscription),
    master_project: Optional[str] = Query(default=None, description="Master project name"),
    project: Optional[str] = Query(default=None, description="Sub-project name (project_name_en)"),
    filter_type: ProjectFilterType = Query(
        default="project", description="Filter type: master, virtual_master, or project"
    ),
):
    """
    Full analytics for a master project, virtual master, or specific sub-project.
    Pass master_project with filter_type=master/virtual_master to aggregate the whole development,
    or project with filter_type=project for a specific sub-project.
    """
    project_name, resolved_filter_type = _resolve_project_scope(
        master_project=master_project, project=project, filter_type=filter_type
    )
    return await get_project_summary(
        project_name=project_name,
        filter_type=resolved_filter_type,
        master_project=master_project,
    )


@router.get("/project/trends", response_model=ProjectTrendsResponse)
async def get_project_trends_endpoint(
    context: AuthContext = Depends(require_active_subscription),
    master_project: Optional[str] = Query(default=None, description="Master project name"),
    project: Optional[str] = Query(default=None, description="Sub-project name (project_name_en)"),
    filter_type: ProjectFilterType = Query(
        default="project", description="Filter type: master, virtual_master, or project"
    ),
    days: int = Query(default=365, description="Number of days to look back"),
):
    """Sales price trend time series for a project, master, or virtual master."""
    project_name, resolved_filter_type = _resolve_project_scope(
        master_project=master_project, project=project, filter_type=filter_type
    )
    return await get_project_trends(
        project_name=project_name, days=days, filter_type=resolved_filter_type
    )


@router.get("/project/forecast", response_model=ProjectForecastResponse)
async def get_project_forecast_endpoint(
    context: AuthContext = Depends(require_active_subscription),
    master_project: Optional[str] = Query(default=None, description="Master project name"),
    project: Optional[str] = Query(default=None, description="Sub-project name (project_name_en)"),
    filter_type: ProjectFilterType = Query(
        default="project", description="Filter type: master, virtual_master, or project"
    ),
    days: int = Query(default=365, description="Number of days to look back"),
):
    project_name, resolved_filter_type = _resolve_project_scope(
        master_project=master_project, project=project, filter_type=filter_type
    )
    return await get_project_forecast(
        project_name=project_name, days=days, filter_type=resolved_filter_type
    )


@router.get("/project/pipeline", response_model=ProjectPipelineResponse)
async def get_project_pipeline_endpoint(
    context: AuthContext = Depends(require_active_subscription),
    master_project: Optional[str] = Query(default=None, description="Master project name"),
    project: Optional[str] = Query(default=None, description="Sub-project name (project_name_en)"),
    filter_type: ProjectFilterType = Query(
        default="project", description="Filter type: master, virtual_master, or project"
    ),
):
    project_name, resolved_filter_type = _resolve_project_scope(
        master_project=master_project, project=project, filter_type=filter_type
    )
    return await get_project_pipeline(project_name=project_name, filter_type=resolved_filter_type)


@router.get(
    "/project/price-distribution",
    response_model=ProjectPriceDistributionResponse,
)
async def get_project_price_distribution_endpoint(
    context: AuthContext = Depends(require_active_subscription),
    master_project: Optional[str] = Query(default=None, description="Master project name"),
    project: Optional[str] = Query(default=None, description="Sub-project name (project_name_en)"),
    filter_type: ProjectFilterType = Query(
        default="project", description="Filter type: master, virtual_master, or project"
    ),
    reg_type: Optional[str] = Query(
        default=None,
        description="Optional registration type filter (e.g. 'Off-Plan Properties')",
    ),
):
    project_name, resolved_filter_type = _resolve_project_scope(
        master_project=master_project, project=project, filter_type=filter_type
    )
    return await get_project_price_distribution(
        project_name=project_name,
        filter_type=resolved_filter_type,
        reg_type=reg_type,
    )
