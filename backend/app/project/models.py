from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class GeoPolygon(BaseModel):
    """Geographic polygon (area boundaries)"""

    coordinates: List[List[float]]  # List of [lng, lat] pairs


class BuildingInfo(BaseModel):
    """Building with property_id for drilldown"""

    property_id: int
    building_number: Optional[str]
    building_name: Optional[str]
    floors: Optional[int]


class GeoPin(BaseModel):
    """Geocoded pin for map display"""

    building_name: str
    project_name: str
    latitude: float
    longitude: float
    property_id: Optional[int] = None
    point_type: Optional[str] = None
    point_number: Optional[str] = None
    floor_count: Optional[int] = None


class MasterProjectSummary(BaseModel):
    """Summary of a sub-project within a master"""

    project_id: int
    project_name: str
    project_status: Optional[str]
    percent_completed: Optional[float]
    no_of_buildings: Optional[int]
    no_of_units: Optional[int]


class MasterProjectResponse(BaseModel):
    """Aggregated data for a master project"""

    master_name: str
    area_name: str
    developer_name: Optional[str]
    total_projects: int
    total_buildings: int
    total_units: int
    projects: List[MasterProjectSummary]
    geo_pins: List[GeoPin]
    unit_composition: List["ProjectUnitComposition"]


class ProjectSearchResult(BaseModel):
    """Minimal project info for search dropdown"""

    project_id: int
    project_name: str
    area_name: str
    developer_name: Optional[str]
    master_project_en: Optional[str]
    latitude: float
    longitude: float


class ProjectUnitComposition(BaseModel):
    """Unit type breakdown"""

    property_sub_type: str  # "Studio", "1 B/R", "2 B/R", "3 B/R", "Penthouse"
    count: int
    percentage: float  # 0-100
    avg_area_sqm: Optional[float]


class BuildingUnitType(BaseModel):
    """Bedroom/type breakdown for a specific building"""

    rooms_en: str  # "Studio", "1 B/R", "2 B/R", etc.
    count: int
    percentage: float
    avg_area_sqm: Optional[float]


class BuildingDetailResponse(BaseModel):
    """Building-level details with unit composition"""

    property_id: int
    building_number: Optional[str]
    floors: Optional[int]
    project_id: int
    project_name: str
    area_name: str
    total_units: int
    unit_composition: List[BuildingUnitType]


class DDAPlotFeature(BaseModel):
    """DDA GIS plot polygon for map overlay."""

    plot_number: str
    project_name: str
    community_name: str
    plot_area_sqm: float
    coordinates: List[List[float]]  # closed ring [[lng, lat], ...]
    land_use_summary: List[str] = []
    max_gfa_sqm: Optional[float] = None
    max_height: Optional[str] = None
    max_coverage: Optional[str] = None
    land_use: Optional[str] = None
    gfa_type: Optional[str] = None
    is_verified: bool = False
    valuation_rate_min_aed_sqft: Optional[float] = None
    valuation_rate_max_aed_sqft: Optional[float] = None
    valuation_min_aed: Optional[float] = None
    valuation_max_aed: Optional[float] = None
    valuation_confidence: Optional[str] = None
    valuation_note: Optional[str] = None
    development_status: str = "no_observed_asset"
    development_confidence: str = "low"
    development_method: str = "no_observed_asset"
    development_note: Optional[str] = None
    linked_asset_count: int = 0
    linked_physical_asset_count: int = 0
    subdivision_plot_count: int = 0
    subdivision_confirmed_count: int = 0


class DDAOutlineFeature(BaseModel):
    """Coarse DDA planning outline for low-zoom map overlay."""

    name: str
    kind: str
    plot_count: int
    total_plot_area_sqm: float
    total_gfa_sqm: float
    coordinates: List[List[float]]  # closed ring [[lng, lat], ...]
    land_use_summary: List[str] = []
    developed_confirmed_count: int = 0
    developed_probable_count: int = 0
    planned_unbuilt_count: int = 0
    no_observed_asset_count: int = 0
    non_developable_count: int = 0
    developed_share: float = 0.0


class ProjectDetailResponse(BaseModel):
    """Full project details for overlay"""

    # Basic info
    project_id: int
    project_name: str
    project_number: Optional[str]
    master_project_en: Optional[str]

    # Location
    area_id: Optional[int]
    area_name: str
    latitude: float
    longitude: float
    area_polygon: Optional[GeoPolygon] = None

    # Developer
    developer_id: Optional[int]
    developer_name: Optional[str]
    master_developer_id: Optional[int]
    master_developer_name: Optional[str]

    # Metrics
    no_of_buildings: Optional[int]
    no_of_units: Optional[int]
    no_of_villas: Optional[int]
    no_of_lands: Optional[int]

    # Timeline
    project_start_date: Optional[date]
    project_end_date: Optional[date]
    completion_date: Optional[date]
    percent_completed: Optional[float]
    project_status: Optional[str]

    # Derived data
    unit_composition: List[ProjectUnitComposition]
    buildings: List[BuildingInfo] = []
    geo_pins: List[GeoPin] = []


class ProjectMarketSnapshotResponse(BaseModel):
    project_id: int
    project_name: str
    area_name: str
    developer_name: Optional[str]
    master_project_en: Optional[str]
    completion_status: str
    pipeline_status: str
    estimated_delivery_confidence: float
    sales_transaction_count_12m: int
    rental_contract_count_12m: int
    total_sales_volume_12m: float
    median_sale_price: Optional[float]
    median_annual_rent: Optional[float]
    gross_yield_pct: Optional[float]
    avg_sale_price_sqm_12m: Optional[float]
    avg_rent_price_sqm_12m: Optional[float]


class ProjectRadarStats(BaseModel):
    """Top-level metrics for the projects radar map."""

    total_projects: int
    mapped_projects: int
    active_projects: int
    finished_projects: int
    pipeline_units: int
    units_delivering_next_12_months: int
    sales_transaction_count_12m: int
    rental_contract_count_12m: int
    total_sales_volume_12m: float
    dda_plot_count: int
    dda_total_plot_area_sqm: float
    dda_total_gfa_sqm: float
    activity_period_days: int = 365
    activity_period_start: Optional[date] = None
    activity_period_end: Optional[date] = None
    activity_source_label: str = "DLD / Ejari"
    sales_transaction_count: int = 0
    rental_contract_count: int = 0
    total_sales_volume: float = 0.0
    mapped_sales_transaction_count: int = 0
    mapped_rental_contract_count: int = 0
    activity_coverage_pct: float = 0.0


class ProjectRadarProject(BaseModel):
    """Mapped project pin with market and delivery signals."""

    project_id: int
    project_name: str
    area_name: str
    developer_name: Optional[str]
    master_project_en: Optional[str]
    latitude: float
    longitude: float
    geo_pin_count: int
    coordinate_source: str = "ch_geo_buildings"
    coordinate_method: Optional[str] = None
    detail_point_count: int = 0
    building_point_count: int = 0
    land_point_count: int = 0
    entity_source: str = "legacy_project"
    supply_status: Optional[str] = None
    supply_completion_date: Optional[date] = None
    units_in_sale: int = 0
    completion_status: str
    pipeline_status: str
    project_status: Optional[str]
    no_of_units: int
    no_of_buildings: int
    percent_completed: Optional[float]
    delivery_confidence: float
    sales_transaction_count_12m: int
    rental_contract_count_12m: int
    total_sales_volume_12m: float
    median_sale_price: Optional[float]
    median_annual_rent: Optional[float]
    gross_yield_pct: Optional[float]
    avg_sale_price_sqm_12m: Optional[float]
    avg_rent_price_sqm_12m: Optional[float]
    sales_transaction_count: int = 0
    rental_contract_count: int = 0
    total_sales_volume: float = 0.0
    avg_sale_price_sqm: Optional[float] = None
    avg_rent_price_sqm: Optional[float] = None


class RadarBuildingPin(BaseModel):
    """Property Finder tower coordinate with linked DLD/Ejari activity."""

    location_id: str
    source_location_id: str
    building_name: str
    project_name: Optional[str] = None
    area_name: str
    latitude: float
    longitude: float
    coordinate_source: str = "property_finder"
    coordinate_precision: str = "tower"
    matched_source_signatures: int = 0
    sales_transaction_count: int = 0
    rental_contract_count: int = 0
    total_sales_volume: float = 0.0
    median_sale_price: Optional[float] = None
    median_annual_rent: Optional[float] = None
    listing_inventory_count: int = 0
    last_activity_date: Optional[date] = None


class ProjectRadarArea(BaseModel):
    """Area-level bubble with supply, demand, and DDA planning context."""

    area_id: int
    area_name: str
    latitude: Optional[float]
    longitude: Optional[float]
    mapped_projects: int
    active_projects: int
    completed_projects: int
    overdue_projects: int
    pipeline_units: int
    units_delivering_next_12_months: int
    active_developers: int
    avg_completion_pct: float
    avg_delivery_confidence: float
    sales_transaction_count_12m: int
    rental_contract_count_12m: int
    total_sales_volume_12m: float
    median_sale_price: Optional[float]
    median_annual_rent: Optional[float]
    avg_sale_price_sqm_12m: Optional[float]
    avg_rent_price_sqm_12m: Optional[float]
    gross_yield_pct: Optional[float]
    top_developers: List[str]
    top_master_projects: List[str]
    dda_plot_count: int
    dda_total_plot_area_sqm: float
    dda_total_gfa_sqm: float
    dda_dominant_land_uses: List[str]
    sales_transaction_count: int = 0
    rental_contract_count: int = 0
    total_sales_volume: float = 0.0
    avg_sale_price_sqm: Optional[float] = None
    avg_rent_price_sqm: Optional[float] = None


class ProjectRadarResponse(BaseModel):
    """Complete payload for the projects radar map."""

    stats: ProjectRadarStats
    projects: List[ProjectRadarProject]
    areas: List[ProjectRadarArea]
    source_notes: List[str]


class ProjectRadarOverviewResponse(BaseModel):
    """Initial radar payload with zone heatmap data only."""

    stats: ProjectRadarStats
    areas: List[ProjectRadarArea]
    source_notes: List[str]
