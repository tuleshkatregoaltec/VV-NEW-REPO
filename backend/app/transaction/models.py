from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    transaction_id: str
    instance_date: Optional[date] = None
    trans_group_en: Optional[str] = None
    procedure_name_en: Optional[str] = None
    property_type_en: Optional[str] = None
    property_sub_type_en: Optional[str] = None
    rooms_en: Optional[str] = None
    area_name_en: Optional[str] = None
    project_name_en: Optional[str] = None
    building_name_en: Optional[str] = None
    procedure_area: Optional[float] = None
    actual_worth: Optional[float] = None
    meter_sale_price: Optional[float] = None
    reg_type_en: Optional[str] = None
    nearest_landmark_en: Optional[str] = None
    nearest_metro_en: Optional[str] = None
    nearest_mall_en: Optional[str] = None


class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int
    limit: int
    offset: int


class RentalContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    contract_id: str
    contract_start_date: Optional[date] = None
    contract_end_date: Optional[date] = None
    ejari_property_type_en: Optional[str] = None
    ejari_property_sub_type_en: Optional[str] = None
    tenant_type_en: Optional[str] = None
    contract_reg_type_en: Optional[str] = None
    area_name_en: Optional[str] = None
    project_name_en: Optional[str] = None
    actual_area: Optional[float] = None
    annual_amount: Optional[float] = None
    contract_amount: Optional[float] = None
    no_of_prop: Optional[int] = None
    is_free_hold: Optional[bool] = None
    nearest_landmark_en: Optional[str] = None
    nearest_metro_en: Optional[str] = None
    nearest_mall_en: Optional[str] = None


class RentalContractListResponse(BaseModel):
    contracts: List[RentalContractResponse]
    total: int
    limit: int
    offset: int


# Transaction matching schemas
class MatchedUnit(BaseModel):
    """A single matched unit with confidence score"""

    model_config = ConfigDict(from_attributes=True)

    unit_id: int
    unit_number: str
    building_number: str
    floor: Optional[str] = None
    actual_area: float
    rooms: Optional[str] = None
    confidence: float  # 0.0 to 1.0
    reasoning: str  # LLM's explanation of why this unit matches


class MatchedUnitsResponse(BaseModel):
    """Response from transaction matching endpoint"""

    transaction_id: str
    transaction_details: TransactionResponse
    matched: bool
    matches: List[MatchedUnit]
    total_candidates: int
    processing_time_seconds: float


class UnitDetails(BaseModel):
    """Basic unit information"""

    unit_number: str
    building_number: str
    actual_area: float
    rooms: Optional[str] = None


class ComparableTransactionItem(BaseModel):
    """Single comparable transaction"""

    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    instance_date: Optional[date] = None
    actual_worth: Optional[float] = None
    meter_sale_price: Optional[float] = None
    building_name_en: Optional[str] = None
    procedure_area: Optional[float] = None


class ComparableTransactionsResponse(BaseModel):
    """Comparable transactions for a specific unit"""

    unit_id: int
    unit_details: UnitDetails
    transactions: List[ComparableTransactionItem]
    total_transactions: int
