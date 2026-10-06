"""Filter options endpoints - redesigned for ClickHouse LowCardinality columns."""

from fastapi import APIRouter, Depends, Query

from app.core.decorators import cached_endpoint
from app.core.dependencies import AuthContext, require_active_subscription
from app.filters.models import FilterOptionsResponse
from app.filters.service import (
    get_rental_filter_options as get_rental_filters_service,
)
from app.filters.service import (
    get_sales_filter_options as get_sales_filters_service,
)

router = APIRouter(prefix="/api/v1/filters", tags=["filters"])


@router.get("/sales", response_model=FilterOptionsResponse)
@cached_endpoint(prefix="filters:sales", expire=3600)
async def get_sales_filter_options(
    context: AuthContext = Depends(require_active_subscription),
    property_usage: str = Query(default=None, description="Residential or Commercial"),
    project: str = Query(default=None, description="Filter buildings by project"),
    filter_type: str = Query(
        default="project",
        description="Project filter type: master, virtual_master, or project",
    ),
    property_type: str = Query(default=None, description="Filter subtypes and rooms"),
    property_sub_type: str = Query(default=None, description="Filter by property sub-type"),
    rooms: str = Query(default=None, description="Filter by room count"),
    registration_type: str = Query(default=None, description="Filter by registration type"),
    area: str = Query(default=None, description="Filter by area"),
    building: str = Query(default=None, description="Filter by building"),
    timeframe_days: int = Query(default=None, description="Days back from today"),
    area_min: float = Query(default=None, description="Minimum property area (sqm)"),
    area_max: float = Query(default=None, description="Maximum property area (sqm)"),
    price_min: float = Query(default=None, description="Minimum price"),
    price_max: float = Query(default=None, description="Maximum price"),
    price_per_sqm_min: float = Query(default=None, description="Minimum price per sqm"),
    price_per_sqm_max: float = Query(default=None, description="Maximum price per sqm"),
):
    """
    Get filter options for sales transactions.

    Optimized for ClickHouse LowCardinality columns (<10ms queries).
    Supports dynamic narrowing (e.g., project → buildings in that project).
    """
    return await get_sales_filters_service(
        property_usage=property_usage,
        project=project,
        filter_type=filter_type,
        property_type=property_type,
        property_sub_type=property_sub_type,
        rooms=rooms,
        registration_type=registration_type,
        area=area,
        building=building,
        timeframe_days=timeframe_days,
        area_min=area_min,
        area_max=area_max,
        price_min=price_min,
        price_max=price_max,
        price_per_sqm_min=price_per_sqm_min,
        price_per_sqm_max=price_per_sqm_max,
    )


@router.get("/rentals", response_model=FilterOptionsResponse)
@cached_endpoint(prefix="filters:rentals", expire=3600)
async def get_rental_filter_options(
    context: AuthContext = Depends(require_active_subscription),
    property_usage: str = Query(default=None, description="Residential or Commercial"),
    project: str = Query(default=None, description="Filter buildings by project"),
    filter_type: str = Query(
        default="project",
        description="Project filter type: master, virtual_master, or project",
    ),
    property_type: str = Query(default=None, description="Filter subtypes"),
    property_sub_type: str = Query(default=None, description="Filter by property sub-type"),
    tenant_type: str = Query(default=None, description="Filter by tenant type"),
    contract_reg_type: str = Query(
        default=None, description="Filter by contract registration type"
    ),
    area: str = Query(default=None, description="Filter by area"),
    timeframe_days: int = Query(default=None, description="Days back from today"),
    area_min: float = Query(default=None, description="Minimum property area (sqm)"),
    area_max: float = Query(default=None, description="Maximum property area (sqm)"),
    rent_min: float = Query(default=None, description="Minimum annual rent"),
    rent_max: float = Query(default=None, description="Maximum annual rent"),
):
    """
    Get filter options for rental contracts.

    Optimized for ClickHouse LowCardinality columns (<10ms queries).
    """
    return await get_rental_filters_service(
        property_usage=property_usage,
        project=project,
        filter_type=filter_type,
        property_type=property_type,
        property_sub_type=property_sub_type,
        tenant_type=tenant_type,
        contract_reg_type=contract_reg_type,
        area=area,
        timeframe_days=timeframe_days,
        area_min=area_min,
        area_max=area_max,
        rent_min=rent_min,
        rent_max=rent_max,
    )
