from typing import List, Optional

from pydantic import BaseModel, Field


class AreaListItem(BaseModel):
    area_name: str
    area_id: Optional[int]
    active_projects: int
    completed_projects: int
    overdue_projects: int
    pipeline_units: int
    units_delivering_next_12_months: int
    active_developers: int
    avg_completion_pct: Optional[float]
    avg_delivery_confidence: Optional[float]
    sales_transaction_count_12m: int
    rental_contract_count_12m: int
    total_sales_volume_12m: float
    median_sale_price: Optional[float]
    median_annual_rent: Optional[float]
    avg_sale_price_sqm_12m: Optional[float]
    avg_rent_price_sqm_12m: Optional[float]
    gross_yield_pct: Optional[float]
    top_developers: List[str] = Field(default_factory=list)


class AreaListResponse(BaseModel):
    areas: List[AreaListItem]
    total: int
    limit: int
    offset: int
    sort_by: str


class AreaDeveloperExposure(BaseModel):
    developer_name: str
    project_count: int
    pipeline_units: int
    total_sales_volume_12m: float
    avg_completion_pct: Optional[float]


class AreaProjectSnapshot(BaseModel):
    project_id: int
    project_name: str
    developer_name: Optional[str]
    master_project_en: Optional[str]
    completion_status: str
    pipeline_status: str
    no_of_units: int
    percent_completed: Optional[float]
    estimated_delivery_confidence: float
    total_sales_volume_12m: float
    median_sale_price: Optional[float]
    median_annual_rent: Optional[float]
    gross_yield_pct: Optional[float]


class AreaDetailResponse(BaseModel):
    area_name: str
    area_id: Optional[int]
    active_projects: int
    completed_projects: int
    overdue_projects: int
    pipeline_units: int
    units_delivering_next_12_months: int
    active_developers: int
    avg_completion_pct: Optional[float]
    avg_delivery_confidence: Optional[float]
    sales_transaction_count_12m: int
    rental_contract_count_12m: int
    total_sales_volume_12m: float
    median_sale_price: Optional[float]
    median_annual_rent: Optional[float]
    avg_sale_price_sqm_12m: Optional[float]
    avg_rent_price_sqm_12m: Optional[float]
    gross_yield_pct: Optional[float]
    top_developers: List[str] = Field(default_factory=list)
    top_master_projects: List[str] = Field(default_factory=list)
    developer_exposure: List[AreaDeveloperExposure] = Field(default_factory=list)
    projects: List[AreaProjectSnapshot] = Field(default_factory=list)
