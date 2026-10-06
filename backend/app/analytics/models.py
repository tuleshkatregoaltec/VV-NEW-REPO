"""Analytics schemas for API responses"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Valid timeframe options
TimeframeDays = Literal[7, 30, 90, 180, 365]


class AnalyticsSummary(BaseModel):
    """Summary KPI metrics for analytics dashboard"""

    transaction_count: int
    total_volume: float
    avg_price: float
    avg_price_sqft: float
    min_price: float
    max_price: float
    volume_change_pct: Optional[float] = None  # % change vs previous period
    count_change_pct: Optional[float] = None


class RentalSummary(BaseModel):
    """Summary KPI metrics for rental analytics"""

    contract_count: int
    total_annual_value: float
    avg_annual_rent: float
    avg_rent_sqft: float
    min_annual_rent: float
    max_annual_rent: float
    value_change_pct: Optional[float] = None
    count_change_pct: Optional[float] = None


class DimensionBreakdown(BaseModel):
    """Breakdown by a specific dimension (property_type, rooms, etc.)"""

    dimension_value: str
    transaction_count: int
    total_volume: float
    avg_price_sqft: float
    pct_of_total: Optional[float] = None


class RentalDimensionBreakdown(BaseModel):
    """Breakdown by a specific dimension for rentals"""

    dimension_value: str
    contract_count: int
    total_annual_value: float
    avg_rent_sqft: float
    pct_of_total: Optional[float] = None


class TrendPoint(BaseModel):
    """Single data point for trend charts"""

    date: date
    count: int
    total_value: float
    avg_value: float
    avg_sqft: float


class AnalyticsResponse(BaseModel):
    """Complete analytics response for dashboard"""

    timeframe_days: int
    property_usage: str
    summary: AnalyticsSummary
    trends: list[TrendPoint]
    by_property_type: list[DimensionBreakdown]
    by_rooms: list[DimensionBreakdown]
    by_reg_type: list[DimensionBreakdown]
    by_master_project: list[DimensionBreakdown]


class RentalAnalyticsResponse(BaseModel):
    """Complete rental analytics response for dashboard"""

    timeframe_days: int
    property_usage: str
    summary: RentalSummary
    trends: list[TrendPoint]
    by_property_type: list[RentalDimensionBreakdown]
    by_master_project: list[RentalDimensionBreakdown]


class MarketTrendPoint(BaseModel):
    """Single data point for the market trend chart"""

    date: date
    transaction_count: int
    avg_price: float
    avg_price_sqm: float


class MarketTrendResponse(BaseModel):
    """Response for the market trend chart endpoint"""

    data: list[MarketTrendPoint]
    total_transactions: int
    avg_price_change_pct: Optional[float] = None
    avg_price_sqm_change_pct: Optional[float] = None


# =============================================================================
# PROJECT ANALYTICS MODELS
# =============================================================================


class ProjectMeta(BaseModel):
    """Metadata from ch_projects + ch_developers"""

    project_name: str
    area_name: Optional[str] = None
    developer_name: Optional[str] = None
    developer_names: list[str] = Field(default_factory=list)
    project_status: Optional[str] = None
    completion_date: Optional[date] = None
    percent_completed: Optional[float] = None
    no_of_units: Optional[int] = None
    no_of_buildings: Optional[int] = None


class ProjectSalesSummary(BaseModel):
    transaction_count: int
    total_volume: float
    avg_price: float
    avg_price_sqm: float
    median_price: float


class ProjectRentalSummary(BaseModel):
    contract_count: int
    total_annual_value: float
    median_annual_rent: float
    median_rent_sqm: float


class RoomAnalytics(BaseModel):
    """Combined sales + rental + yield metrics per bedroom count"""

    rooms: str
    sale_count: int
    avg_sale_price: float
    avg_sale_price_sqm: float
    rental_count: int
    median_annual_rent: float
    median_rent_sqm: float
    gross_yield_pct: Optional[float] = None


class ProjectConfigurationRow(BaseModel):
    market_segment: Literal["all", "off_plan", "secondary"]
    rooms: str
    stock_units: int
    sale_count: int
    sales_last_12m: int
    avg_sale_price: float
    median_sale_price: float
    avg_sale_price_sqm: float
    avg_unit_size_sqm: float
    rental_count: int
    median_annual_rent: float
    median_rent_sqm: float
    gross_yield_pct: Optional[float] = None
    price_change_yoy_pct: Optional[float] = None
    sales_momentum_pct: Optional[float] = None
    absorption_rate_pct: Optional[float] = None
    price_p25: float
    price_p50: float
    price_p75: float


class PropertyTypeBreakdown(BaseModel):
    property_type: str
    count: int
    avg_price: float
    pct_of_total: float


class RegTypeBreakdown(BaseModel):
    reg_type: str
    count: int
    avg_price: float
    pct_of_total: float


class AnalyticsUnitComposition(BaseModel):
    rooms: str
    count: int
    pct_of_total: float
    avg_unit_size_sqm: float = 0.0


class ProjectAnalyticsResponse(BaseModel):
    """Full analytics response for a single project"""

    project: Optional[ProjectMeta] = None
    sales: ProjectSalesSummary
    rentals: ProjectRentalSummary
    overall_gross_yield_pct: Optional[float] = None
    by_rooms: list[RoomAnalytics]
    by_property_type: list[PropertyTypeBreakdown]
    by_reg_type: list[RegTypeBreakdown]
    unit_composition: list[AnalyticsUnitComposition]
    configuration_analysis: list[ProjectConfigurationRow]


class ProjectTrendPoint(BaseModel):
    date: date
    transaction_count: int
    avg_price: float
    avg_price_sqm: float


class ProjectTrendsResponse(BaseModel):
    data: list[ProjectTrendPoint]


class ProjectForecastPoint(BaseModel):
    date: date
    avg_price: float
    avg_price_sqm: float
    series: Literal["historical", "forecast"]


class ProjectForecastResponse(BaseModel):
    data: list[ProjectForecastPoint]
    delivery_date: Optional[date] = None
    source_reg_type: str = "Off-Plan Properties"
    methodology: str


class ProjectPipelinePoint(BaseModel):
    period: date
    existing_stock_units: int
    carried_stock_units: int
    new_pipeline_units: int


class ProjectPipelineResponse(BaseModel):
    area_name: Optional[str] = None
    developer_name: Optional[str] = None
    data: list[ProjectPipelinePoint]


class PriceDistributionBucket(BaseModel):
    """Mean + population std dev for a single bedroom type."""

    rooms: str
    sale_count: int
    mean_price: float
    std_price: float
    log_mean_price: float = 0.0
    log_std_price: float = 0.0
    p05_price: float = 0.0
    p25_price: float = 0.0
    p50_price: float = 0.0
    p75_price: float = 0.0
    p95_price: float = 0.0
    mean_price_sqm: float
    std_price_sqm: float


class ProjectPriceDistributionResponse(BaseModel):
    """Price distribution by bedroom type, including an all-rooms aggregate."""

    all: Optional[PriceDistributionBucket] = None
    by_rooms: list[PriceDistributionBucket]


class ProjectSearchItem(BaseModel):
    name: str
    filter_type: str  # "master" | "virtual_master" | "project"


class ProjectSearchResponse(BaseModel):
    projects: list[ProjectSearchItem]


class SubProjectItem(BaseModel):
    name: str
    transaction_count: int


class SubProjectsResponse(BaseModel):
    sub_projects: list[SubProjectItem]
