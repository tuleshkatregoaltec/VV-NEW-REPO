from fastapi import APIRouter, Depends, HTTPException

from app.area.models import AreaDetailResponse, AreaListResponse
from app.area.service import get_area_detail, list_areas
from app.core.decorators import cached_endpoint
from app.core.dependencies import AuthContext, require_active_subscription

router = APIRouter(prefix="/api/v1/areas", tags=["areas"])


@router.get("", response_model=AreaListResponse)
@cached_endpoint(prefix="areas_list_v2", expire=3600)
async def areas_list(
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "units",
    search: str | None = None,
    context: AuthContext = Depends(require_active_subscription),
):
    return await list_areas(limit=limit, offset=offset, sort_by=sort_by, search=search)


@router.get("/{area_name}", response_model=AreaDetailResponse)
@cached_endpoint(prefix="area_detail_v1", expire=3600)
async def area_detail(
    area_name: str,
    context: AuthContext = Depends(require_active_subscription),
):
    try:
        return await get_area_detail(area_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
