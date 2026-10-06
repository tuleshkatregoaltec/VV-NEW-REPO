from enum import IntEnum
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.decorators import cached_endpoint
from app.core.dependencies import AuthContext, require_active_subscription
from app.project.models import (
    BuildingDetailResponse,
    DDAOutlineFeature,
    DDAPlotFeature,
    MasterProjectResponse,
    ProjectDetailResponse,
    ProjectRadarOverviewResponse,
    ProjectRadarProject,
    ProjectRadarResponse,
    ProjectSearchResult,
    RadarBuildingPin,
)
from app.project.service import (
    get_building_details,
    get_dda_outlines_for_bounds,
    get_dda_plots_for_area,
    get_master_project,
    get_project_details,
    get_project_radar,
    get_project_radar_overview,
    get_project_radar_pins,
    get_radar_building_pins,
    list_all_projects,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class RadarPeriodDays(IntEnum):
    """Supported Radar windows, parsed from their query-string representation."""

    DAYS_30 = 30
    DAYS_90 = 90
    DAYS_180 = 180
    DAYS_365 = 365


@router.get("/list", response_model=List[ProjectSearchResult])
@cached_endpoint(prefix="project_list", expire=3600)  # 1 hour
async def list_projects(context: AuthContext = Depends(require_active_subscription)):
    """Get all projects for client-side search"""
    return await list_all_projects()


@router.get("/radar", response_model=ProjectRadarResponse)
@cached_endpoint(prefix="project_radar_ph_box", expire=1800)
async def project_radar(
    limit: int = Query(default=1400, ge=100, le=5000, description="Maximum mapped projects"),
    period_days: RadarPeriodDays = Query(
        default=365,
        description="Trailing DLD/Ejari activity window in days (maximum 365)",
    ),
    context: AuthContext = Depends(require_active_subscription),
):
    """Get mapped project, area, and planning signals for the radar view."""
    return await get_project_radar(limit=limit, period_days=period_days)


@router.get("/radar/overview", response_model=ProjectRadarOverviewResponse)
@cached_endpoint(prefix="project_radar_overview_ph_box", expire=1800)
async def project_radar_overview(
    period_days: RadarPeriodDays = Query(
        default=365,
        description="Trailing DLD/Ejari activity window in days (maximum 365)",
    ),
    context: AuthContext = Depends(require_active_subscription),
):
    """Get lightweight radar stats and area heatmap data without project pins."""
    return await get_project_radar_overview(period_days=period_days)


@router.get("/radar/pins", response_model=List[ProjectRadarProject])
@cached_endpoint(prefix="project_radar_pins_ph_box", expire=600)
async def project_radar_pins(
    west: Optional[float] = Query(None, ge=54, le=57, description="Viewport west longitude"),
    south: Optional[float] = Query(None, ge=24, le=26, description="Viewport south latitude"),
    east: Optional[float] = Query(None, ge=54, le=57, description="Viewport east longitude"),
    north: Optional[float] = Query(None, ge=24, le=26, description="Viewport north latitude"),
    area: Optional[str] = Query(None, description="Area name to fetch pins for"),
    developer: Optional[str] = Query(None, description="Developer name to focus"),
    limit: int = Query(default=700, ge=10, le=2500, description="Maximum project pins"),
    period_days: RadarPeriodDays = Query(
        default=365,
        description="Trailing DLD/Ejari activity window in days (maximum 365)",
    ),
    context: AuthContext = Depends(require_active_subscription),
):
    """Get bounded project pins for a viewport, selected area, or developer overlay."""
    bbox_values = [west, south, east, north]
    if any(value is not None for value in bbox_values) and any(
        value is None for value in bbox_values
    ):
        raise HTTPException(
            status_code=400, detail="Viewport bounds must include west, south, east, and north"
        )
    return await get_project_radar_pins(
        west=west,
        south=south,
        east=east,
        north=north,
        area=area,
        developer=developer,
        limit=limit,
        period_days=period_days,
    )


@router.get("/radar/building-pins", response_model=List[RadarBuildingPin])
@cached_endpoint(prefix="project_radar_building_pins_ph_box", expire=600)
async def radar_building_pins(
    west: float = Query(..., ge=54, le=57, description="Viewport west longitude"),
    south: float = Query(..., ge=24, le=26, description="Viewport south latitude"),
    east: float = Query(..., ge=54, le=57, description="Viewport east longitude"),
    north: float = Query(..., ge=24, le=26, description="Viewport north latitude"),
    limit: int = Query(default=3000, ge=10, le=10000, description="Maximum tower pins"),
    period_days: RadarPeriodDays = Query(
        default=365,
        description="Trailing DLD/Ejari activity window in days (maximum 365)",
    ),
    context: AuthContext = Depends(require_active_subscription),
):
    """Get Property Finder tower pins and linked market evidence for a viewport."""
    if west >= east or south >= north:
        raise HTTPException(status_code=400, detail="Viewport bounds are invalid")
    return await get_radar_building_pins(
        west=west,
        south=south,
        east=east,
        north=north,
        limit=limit,
        period_days=period_days,
    )


@router.get("/master", response_model=MasterProjectResponse)
@cached_endpoint(prefix="master_project", expire=1800)  # 30 minutes
async def master_project(
    name: str = Query(..., description="master_project_en value"),
    context: AuthContext = Depends(require_active_subscription),
):
    """Get aggregated data for a master project and its sub-projects"""
    master = await get_master_project(name)
    if not master:
        raise HTTPException(status_code=404, detail="Master project not found")
    return master


@router.get("/building/{property_id}", response_model=BuildingDetailResponse)
@cached_endpoint(prefix="building_details", expire=1800)  # 30 minutes
async def building_details(
    property_id: int, context: AuthContext = Depends(require_active_subscription)
):
    """Get building details with unit composition by bedroom type"""
    building = await get_building_details(property_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return building


@router.get("/dda-plots", response_model=List[DDAPlotFeature])
@cached_endpoint(prefix="dda_plots", expire=3600)  # 1 hour — plot data changes rarely
async def get_dda_plots(
    area: Optional[str] = Query(
        None, description="Area or community name to match against DDA plots"
    ),
    west: Optional[float] = Query(None, ge=54, le=57, description="Viewport west longitude"),
    south: Optional[float] = Query(None, ge=24, le=26, description="Viewport south latitude"),
    east: Optional[float] = Query(None, ge=54, le=57, description="Viewport east longitude"),
    north: Optional[float] = Query(None, ge=24, le=26, description="Viewport north latitude"),
    limit: int = Query(default=1200, ge=100, le=5000, description="Maximum DDA plots to return"),
    include_valuations: bool = Query(
        default=False,
        description="Include transaction-derived valuation ranges. Disabled for bulk map rendering.",
    ),
    context: AuthContext = Depends(require_active_subscription),
):
    """Get DDA GIS plot polygons for a community or current map viewport."""
    return await get_dda_plots_for_area(
        area=area,
        west=west,
        south=south,
        east=east,
        north=north,
        limit=limit,
        include_valuations=include_valuations,
    )


@router.get("/dda-outlines", response_model=List[DDAOutlineFeature])
@cached_endpoint(prefix="dda_outlines", expire=3600)
async def get_dda_outlines(
    west: float = Query(..., ge=54, le=57, description="Viewport west longitude"),
    south: float = Query(..., ge=24, le=26, description="Viewport south latitude"),
    east: float = Query(..., ge=54, le=57, description="Viewport east longitude"),
    north: float = Query(..., ge=24, le=26, description="Viewport north latitude"),
    zoom: float = Query(..., ge=1, le=22, description="Current map zoom"),
    limit: int = Query(default=160, ge=20, le=500, description="Maximum outlines to return"),
    context: AuthContext = Depends(require_active_subscription),
):
    """Get coarse DDA planning outlines for low-zoom map context."""
    return await get_dda_outlines_for_bounds(
        west=west,
        south=south,
        east=east,
        north=north,
        zoom=zoom,
        limit=limit,
    )


@router.get("/{project_id}", response_model=ProjectDetailResponse)
@cached_endpoint(prefix="project_details_ph_box", expire=1800)  # 30 minutes
async def project_details(
    project_id: int, context: AuthContext = Depends(require_active_subscription)
):
    """Get full project details with unit composition"""
    project = await get_project_details(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
