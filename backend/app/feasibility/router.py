from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import AuthContext, require_active_subscription
from app.feasibility.models import (
    ComparableData,
    FeasibilityChatRequest,
    FeasibilitySavedStudyListItem,
    FeasibilitySavedStudyResponse,
    FeasibilityStudyCreateRequest,
    FeasibilityStudyUpdateRequest,
    GenerateStudyRequest,
    GenerateStudyResponse,
    LandSaleEvidence,
    Plot,
    PlotDetails,
    PlotResearch,
    Usage,
)
from app.feasibility.service import (
    create_saved_study,
    delete_saved_study,
    generate_hbu_for_plot,
    generate_seeded_study,
    get_comparable_or_404,
    get_plot_details_or_404,
    get_plot_land_sales_or_404,
    get_saved_study,
    list_nearby_land_plots,
    list_plot_communities,
    list_saved_studies,
    list_transaction_areas,
    search_gis_plots,
    search_nearby_land_plots,
    stream_chat_events,
    update_saved_study,
)
from app.postgres import get_db_session

router = APIRouter(prefix="/api/v1/feasibility", tags=["feasibility"])


def _auth_ids(auth: AuthContext) -> tuple[str, str]:
    return str(auth.user.id), str(auth.organization.id)


@router.get("/areas", response_model=list[str])
async def areas_endpoint(
    _: AuthContext = Depends(require_active_subscription),
):
    """Get all distinct transaction areas with sales activity."""
    return await list_transaction_areas()


@router.get("/communities", response_model=list[str])
async def communities_endpoint(
    _: AuthContext = Depends(require_active_subscription),
):
    """Get GIS plot communities ordered by activity."""
    return await list_plot_communities()


@router.get("/studies", response_model=list[FeasibilitySavedStudyListItem])
async def studies_endpoint(
    auth: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """List saved feasibility studies for the authenticated user and organization."""
    user_id, organization_id = _auth_ids(auth)
    return await list_saved_studies(db, user_id=user_id, organization_id=organization_id)


@router.post("/studies", response_model=FeasibilitySavedStudyResponse, status_code=201)
async def create_study_endpoint(
    request: FeasibilityStudyCreateRequest,
    auth: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a saved feasibility study from the selected plot and generated snapshots."""
    user_id, organization_id = _auth_ids(auth)
    return await create_saved_study(
        db,
        request=request,
        user_id=user_id,
        organization_id=organization_id,
    )


@router.get("/studies/{study_id}", response_model=FeasibilitySavedStudyResponse)
async def get_study_endpoint(
    study_id: int,
    auth: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a saved feasibility study owned by the current user and organization."""
    user_id, organization_id = _auth_ids(auth)
    return await get_saved_study(
        db,
        study_id=study_id,
        user_id=user_id,
        organization_id=organization_id,
    )


@router.patch("/studies/{study_id}", response_model=FeasibilitySavedStudyResponse)
async def update_study_endpoint(
    study_id: int,
    request: FeasibilityStudyUpdateRequest,
    auth: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """Patch saved feasibility study inputs and metadata."""
    user_id, organization_id = _auth_ids(auth)
    return await update_saved_study(
        db,
        study_id=study_id,
        request=request,
        user_id=user_id,
        organization_id=organization_id,
    )


@router.delete("/studies/{study_id}", status_code=204)
async def delete_study_endpoint(
    study_id: int,
    auth: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a saved feasibility study owned by the current user and organization."""
    user_id, organization_id = _auth_ids(auth)
    await delete_saved_study(
        db,
        study_id=study_id,
        user_id=user_id,
        organization_id=organization_id,
    )
    return Response(status_code=204)


@router.get("/plots", response_model=list[Plot])
async def plots_endpoint(
    q: str = Query(default=""),
    community: str = Query(default=""),
    min_plot_area_sqm: float | None = Query(default=None, ge=0.0),
    max_plot_area_sqm: float | None = Query(default=None, ge=0.0),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    _: AuthContext = Depends(require_active_subscription),
):
    """Search GIS plots by plot number, project, community, and plot area."""
    return await search_gis_plots(
        q=q,
        community=community,
        min_plot_area_sqm=min_plot_area_sqm,
        max_plot_area_sqm=max_plot_area_sqm,
        offset=offset,
        limit=limit,
    )


@router.get("/plots/{plot_number}", response_model=PlotDetails)
async def plot_details_endpoint(
    plot_number: str,
    _: AuthContext = Depends(require_active_subscription),
):
    """Get full GIS-backed plot data for feasibility and HBU analysis."""
    return await get_plot_details_or_404(plot_number)


@router.post("/hbu/{plot_number}", response_model=PlotResearch)
async def generate_hbu_endpoint(
    plot_number: str,
    usage_override: Usage | None = Query(default=None),
    _: AuthContext = Depends(require_active_subscription),
):
    """Generate an agent-authored initial HBU study for the selected GIS plot."""
    return await generate_hbu_for_plot(plot_number, usage_override=usage_override)


@router.get("/plots/{plot_number}/land-sales", response_model=list[LandSaleEvidence])
async def plot_land_sales_endpoint(
    plot_number: str,
    days: int = Query(default=1825, ge=30, le=3650),
    limit: int = Query(default=12, ge=1, le=50),
    _: AuthContext = Depends(require_active_subscription),
):
    """Get recent land sale evidence for the selected GIS plot area."""
    return await get_plot_land_sales_or_404(
        plot_number=plot_number,
        days=days,
        limit=limit,
    )


@router.get("/land", response_model=list[Plot])
async def land_endpoint(
    area: str = Query(...),
    size_sqm: float = Query(...),
    tolerance: float = Query(default=0.25, ge=0.0, le=1.0),
    _: AuthContext = Depends(require_active_subscription),
):
    """Find land plots near a given size in the specified area."""
    return await list_nearby_land_plots(area, size_sqm, tolerance)


@router.get("/land/search", response_model=list[Plot])
async def land_search_endpoint(
    area: str = Query(...),
    q: str = Query(..., min_length=1),
    _: AuthContext = Depends(require_active_subscription),
):
    """Legacy plot search alias backed by GIS plot data."""
    return await search_nearby_land_plots(area, q)


@router.get("/comparable", response_model=ComparableData)
async def comparable_endpoint(
    project_ids: str = Query(..., description="Comma-separated project IDs"),
    _: AuthContext = Depends(require_active_subscription),
):
    """Get aggregated comparable data for a set of projects."""
    return await get_comparable_or_404(project_ids)


@router.post("/generate-study", response_model=GenerateStudyResponse)
async def generate_study_endpoint(
    request: GenerateStudyRequest,
    _: AuthContext = Depends(require_active_subscription),
):
    """Generate an initial feasibility study for the selected GIS plot."""
    return await generate_seeded_study(request)


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
)
async def chat_stream_endpoint(
    request: FeasibilityChatRequest,
    _: AuthContext = Depends(require_active_subscription),
):
    """Stream LLM feasibility assistant response via SSE."""
    return StreamingResponse(
        stream_chat_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
