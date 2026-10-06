from fastapi import APIRouter, Depends, Query

from app.core.dependencies import AuthContext, require_active_subscription
from app.listings.models import (
    ListingAnalyticsResponse,
    ListingAssetClass,
    ListingDetailResponse,
    ListingFiltersResponse,
    ListingListResponse,
    ListingMode,
)
from app.listings.service import (
    get_listing_from_clickhouse,
    list_listings_from_clickhouse,
    listing_analytics_from_clickhouse,
    listing_filters_from_clickhouse,
)

router = APIRouter(prefix="/api/v1/listings", tags=["listings"])


@router.get("", response_model=ListingListResponse)
async def list_listings(
    mode: ListingMode = Query(default="rent"),
    asset_class: ListingAssetClass | None = Query(default=None),
    limit: int = Query(default=48, ge=1, le=120),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=160),
    area: str | None = Query(default=None, max_length=160),
    property_type: str | None = Query(default=None, max_length=120),
    bedrooms: str | None = Query(default=None, max_length=40),
    price_min: int | None = Query(default=None, ge=0),
    price_max: int | None = Query(default=None, ge=0),
    context: AuthContext = Depends(require_active_subscription),
):
    """List Property Finder listings from ph_box ClickHouse."""
    return await list_listings_from_clickhouse(
        mode=mode,
        asset_class=asset_class,
        limit=limit,
        offset=offset,
        search=search,
        area=area,
        property_type=property_type,
        bedrooms=bedrooms,
        price_min=price_min,
        price_max=price_max,
        price_basis="annual" if mode == "rent" else "raw",
        include_filters=False,
    )


@router.get("/filters", response_model=ListingFiltersResponse)
async def listing_filters(
    mode: ListingMode = Query(default="rent"),
    asset_class: ListingAssetClass | None = Query(default=None),
    context: AuthContext = Depends(require_active_subscription),
):
    """Return dropdown options independently from paginated inventory."""
    return await listing_filters_from_clickhouse(mode=mode, asset_class=asset_class)


@router.get("/analytics", response_model=ListingAnalyticsResponse)
async def listing_analytics(
    mode: ListingMode = Query(default="rent"),
    asset_class: ListingAssetClass | None = Query(default=None),
    search: str | None = Query(default=None, max_length=160),
    area: str | None = Query(default=None, max_length=160),
    property_type: str | None = Query(default=None, max_length=120),
    bedrooms: str | None = Query(default=None, max_length=40),
    price_min: int | None = Query(default=None, ge=0),
    price_max: int | None = Query(default=None, ge=0),
    context: AuthContext = Depends(require_active_subscription),
):
    """Aggregate metrics for the current Property Finder listing filters."""
    return await listing_analytics_from_clickhouse(
        mode=mode,
        asset_class=asset_class,
        search=search,
        area=area,
        property_type=property_type,
        bedrooms=bedrooms,
        price_min=price_min,
        price_max=price_max,
    )


@router.get("/{listing_id}", response_model=ListingDetailResponse)
async def get_listing(
    listing_id: str,
    context: AuthContext = Depends(require_active_subscription),
):
    """Get one Property Finder listing from ph_box ClickHouse."""
    return await get_listing_from_clickhouse(listing_id)
