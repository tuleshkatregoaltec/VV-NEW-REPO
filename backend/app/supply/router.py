from fastapi import APIRouter, Depends, Query

from app.core.decorators import cached_endpoint
from app.core.dependencies import AuthContext, require_active_subscription
from app.supply.models import (
    DeveloperRankingsResponse,
    SupplyCatalogueProjectDetailResponse,
    SupplyCatalogueProjectsResponse,
    UpcomingProjectResponse,
    UpcomingProjectsResponse,
)
from app.supply.service import (
    get_developer_rankings,
    get_supply_catalogue_project,
    get_upcoming_projects_ch,
    list_supply_catalogue_projects,
)

router = APIRouter(prefix="/api/v1/supply", tags=["supply"])


@router.get("/developer-rankings", response_model=DeveloperRankingsResponse)
@cached_endpoint(prefix="supply:developer_rankings", expire=1800)
async def list_developer_rankings(
    period: str = Query(default="1y", pattern="^(ytd|1y|3y|5y)$"),
    metric: str = Query(default="proprietary_score", max_length=80),
    limit: int = Query(default=25, ge=5, le=100),
    context: AuthContext = Depends(require_active_subscription),
):
    """Rank developers using DLD project/transaction signals."""
    return await get_developer_rankings(
        period=period,
        metric=metric,
        limit=limit,
    )


@router.get("/upcoming-projects", response_model=UpcomingProjectsResponse)
@cached_endpoint(prefix="upcoming_projects:v2", expire=3600)
async def list_upcoming_projects(
    context: AuthContext = Depends(require_active_subscription),
):
    """Get all upcoming/active projects for catalogue view."""
    projects = await get_upcoming_projects_ch()

    # Build response
    result = []
    for project in projects:
        project_data = {
            "project_id": project.get("project_id"),
            "project_name": project.get("project_name_en")
            or project.get("project_name_ar")
            or "Unknown",
            "developer_name": project.get("developer_name") or "Unknown",
            "developer_id": project.get("developer_id"),
            "area_name": project.get("area_name_en") or "Unknown",
            "project_start_date": project.get("project_start_date"),
            "project_end_date": project.get("project_end_date"),
            "percent_completed": project.get("percent_completed") or 0,
            "no_of_buildings": project.get("no_of_buildings"),
            "no_of_units": project.get("no_of_units"),
        }
        result.append(UpcomingProjectResponse.model_validate(project_data))

    return UpcomingProjectsResponse(projects=result, total=len(result))


@router.get("/catalogue/projects", response_model=SupplyCatalogueProjectsResponse)
@cached_endpoint(prefix="supply:catalogue_projects", expire=1800)
async def list_catalogue_projects(
    limit: int = Query(default=48, ge=1, le=120),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=120),
    area: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, max_length=80),
    developer: str | None = Query(default=None, max_length=160),
    sort: str = Query(
        default="recommended",
        pattern="^(recommended|newest|price_low|price_high|delivery_soon|delivery_latest)$",
    ),
    include_past: bool = Query(default=False),
    context: AuthContext = Depends(require_active_subscription),
):
    """List the ph_box Reelly supply catalogue."""
    return await list_supply_catalogue_projects(
        limit=limit,
        offset=offset,
        search=search,
        area=area,
        status=status,
        developer=developer,
        sort=sort,
        include_past=include_past,
    )


@router.get("/catalogue/projects/{project_id}", response_model=SupplyCatalogueProjectDetailResponse)
async def get_catalogue_project(
    project_id: int,
    context: AuthContext = Depends(require_active_subscription),
):
    """Get one ph_box Reelly supply catalogue project."""
    return await get_supply_catalogue_project(None, project_id)
