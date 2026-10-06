"""Response types for ClickHouse data (API contracts only).

These are NOT database models. They represent the shape of data
returned from ClickHouse queries for API responses.

Column names match ClickHouse schema exactly - no renaming.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

# =============================================================================
# ANALYTICS RESPONSES
# =============================================================================


class SalesSummary(BaseModel):
    """Summary statistics for sales analytics."""

    transaction_count: int
    median_price: Decimal
    avg_price: Decimal
    total_volume: Decimal
    median_price_per_sqm: Decimal
    median_area_sqm: Decimal


class RentalSummary(BaseModel):
    """Summary statistics for rental analytics."""

    contract_count: int
    median_rent: Decimal
    avg_rent: Decimal
    total_annual_value: Decimal
    median_rent_per_sqm: Decimal
    median_area_sqm: Decimal


class AreaStats(BaseModel):
    """Sales statistics for an area."""

    area_name_en: str
    transaction_count: int
    median_price: Decimal
    total_volume: Decimal


class PriceTrend(BaseModel):
    """Price trend for a time period."""

    period: date
    transaction_count: int
    median_price: Decimal
    avg_price: Decimal


class PropertyTypeBreakdown(BaseModel):
    """Breakdown by property type."""

    property_type_en: str
    transaction_count: int
    median_price: Decimal
    total_volume: Decimal


class RoomsBreakdown(BaseModel):
    """Breakdown by room count."""

    rooms_en: str
    transaction_count: int
    median_price: Decimal
    avg_price: Decimal


# =============================================================================
# PROJECTS RESPONSES
# =============================================================================


class ProjectListItem(BaseModel):
    """Project summary for listings."""

    project_id: int
    project_number: str
    project_name_en: str
    project_name_ar: Optional[str] = None
    master_project_en: Optional[str] = None
    master_project_id: Optional[int] = None
    developer_id: Optional[int] = None
    area_id: Optional[int] = None
    area_name_en: Optional[str] = None
    property_usage_en: Optional[str] = None
    is_free_hold: Optional[bool] = None
    project_status: Optional[str] = None
    total_units: Optional[int] = None
    total_buildings: Optional[int] = None
    total_villas: Optional[int] = None
    completion_date: Optional[date] = None


class ProjectDetails(BaseModel):
    """Full project details."""

    project_id: int
    project_number: str
    project_name_en: str
    project_name_ar: Optional[str] = None
    master_project_en: Optional[str] = None
    master_project_id: Optional[int] = None
    developer_id: Optional[int] = None
    master_developer_id: Optional[int] = None
    area_id: Optional[int] = None
    area_name_en: Optional[str] = None
    property_usage_en: Optional[str] = None
    is_free_hold: Optional[bool] = None

    # Project Status & Timeline
    project_status: Optional[str] = None
    project_start_date: Optional[date] = None
    completion_date: Optional[date] = None
    project_end_date: Optional[date] = None
    cancellation_date: Optional[date] = None
    percent_completed: Optional[float] = None

    # Project Composition
    total_units: Optional[int] = None
    total_buildings: Optional[int] = None
    total_villas: Optional[int] = None

    # Regulatory
    escrow_agent_name: Optional[str] = None
    zoning_authority_en: Optional[str] = None


class DeveloperListItem(BaseModel):
    """Developer summary for listings."""

    developer_id: int
    developer_number: str
    name_en: str
    name_ar: Optional[str] = None


class BuildingListItem(BaseModel):
    """Building summary for listings."""

    building_id: int
    building_number: Optional[str] = None
    building_name_en: str
    building_name_ar: Optional[str] = None
    project_id: Optional[int] = None
    project_number: Optional[str] = None
    project_name_en: Optional[str] = None
    property_usage_en: Optional[str] = None
    bld_levels: Optional[int] = None
    floors: Optional[int] = None
    units: Optional[int] = None


class UnitListItem(BaseModel):
    """Unit summary for listings."""

    unit_id: int
    unit_number: Optional[str] = None
    unit_name_en: Optional[str] = None
    building_id: Optional[int] = None
    building_name_en: Optional[str] = None
    project_id: Optional[int] = None
    project_number: Optional[str] = None
    project_name_en: Optional[str] = None
    property_type_en: Optional[str] = None
    property_usage_en: Optional[str] = None
    rooms_en: Optional[str] = None
    actual_area: Optional[Decimal] = None
    floor: Optional[str] = None


# =============================================================================
# COMPARABLES RESPONSES
# =============================================================================


class ComparableUnit(BaseModel):
    """Comparable unit for valuation."""

    unit_id: int
    project_number: Optional[str] = None
    project_name_en: Optional[str] = None
    building_id: Optional[int] = None
    building_name_en: Optional[str] = None
    property_type_en: Optional[str] = None
    property_sub_type_en: Optional[str] = None
    rooms_en: Optional[str] = None
    actual_area: Optional[Decimal] = None
    floor: Optional[str] = None


class ComparableTransaction(BaseModel):
    """Comparable transaction for valuation."""

    transaction_id: str
    instance_date: date
    property_type_en: str
    property_sub_type_en: Optional[str] = None
    rooms_en: Optional[str] = None
    actual_worth: Decimal
    procedure_area: Decimal
    meter_sale_price: Decimal
    master_project_en: Optional[str] = None
    area_name_en: Optional[str] = None
    nearest_metro_en: Optional[str] = None
    nearest_landmark_en: Optional[str] = None


class ComparableRentalContract(BaseModel):
    """Comparable rental contract for valuation."""

    contract_id: str
    line_number: int
    contract_start_date: date
    property_type_en: Optional[str] = None
    property_sub_type_en: Optional[str] = None
    rooms_en: Optional[str] = None
    annual_amount: Decimal
    actual_area: Decimal
    rent_per_sqm: Decimal
    master_project_en: Optional[str] = None
    area_name_en: Optional[str] = None


# =============================================================================
# FILTER RESPONSES
# =============================================================================


class FilterOption(BaseModel):
    """Single filter option value."""

    value: str
    label: Optional[str] = None  # Can be same as value if not provided


class FilterOptions(BaseModel):
    """Collection of filter options for dropdowns."""

    property_types: List[str] = Field(default_factory=list)
    property_sub_types: List[str] = Field(default_factory=list)
    areas: List[str] = Field(default_factory=list)
    master_projects: List[str] = Field(default_factory=list)
    rooms: List[str] = Field(default_factory=list)
    reg_types: List[str] = Field(default_factory=list)


# =============================================================================
# TRANSACTION & RENTAL RESPONSES
# =============================================================================


class TransactionDetail(BaseModel):
    """Full transaction details."""

    transaction_id: str
    property_usage_en: str
    instance_date: date

    # Property details
    property_type_en: str
    property_sub_type_en: Optional[str] = None
    rooms_en: Optional[str] = None
    reg_type_en: Optional[str] = None

    # Location
    master_project_en: Optional[str] = None
    area_name_en: Optional[str] = None
    area_id: Optional[int] = None
    project_name_en: Optional[str] = None
    project_number: Optional[str] = None
    building_name_en: Optional[str] = None

    # Metrics
    procedure_area: Decimal
    has_parking: bool
    actual_worth: Decimal
    meter_sale_price: Decimal

    # Landmarks
    nearest_landmark_en: Optional[str] = None
    nearest_metro_en: Optional[str] = None
    nearest_mall_en: Optional[str] = None

    # Buckets
    price_bucket: Optional[str] = None
    area_bucket: Optional[str] = None
    price_sqft_bucket: Optional[str] = None


class RentalContractDetail(BaseModel):
    """Full rental contract details."""

    contract_id: str
    line_number: int
    property_usage_en: str
    contract_start_date: date

    # Property details
    ejari_property_type_en: Optional[str] = None
    ejari_property_sub_type_en: Optional[str] = None
    contract_reg_type_en: Optional[str] = None
    tenant_type_en: Optional[str] = None

    # Location
    master_project_en: Optional[str] = None
    area_name_en: Optional[str] = None
    area_id: Optional[int] = None
    project_name_en: Optional[str] = None
    project_number: Optional[str] = None

    # Metrics
    annual_amount: Decimal
    actual_area: Decimal
    rent_per_sqm: Decimal
    contract_end_date: Optional[date] = None

    # Landmarks
    nearest_landmark_en: Optional[str] = None
    nearest_metro_en: Optional[str] = None
    nearest_mall_en: Optional[str] = None

    # Buckets
    rent_bucket: Optional[str] = None
    area_bucket: Optional[str] = None
    rent_sqft_bucket: Optional[str] = None
