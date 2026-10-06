from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

LeadStatus = Literal["expired", "expiring_30", "expiring_60", "expiring_90"]
LeadPriority = Literal["urgent", "high", "medium"]
MatchConfidence = Literal["high", "medium", "low"]
CrmAssetClass = Literal["residential", "commercial", "other"]
CrmPipelineStatus = Literal[
    "new",
    "researching",
    "contact_ready",
    "contacted",
    "qualified",
    "nurture",
    "won",
    "closed",
]
CrmHighlightColor = Literal["none", "amber", "green", "blue", "red", "purple"]


class CrmLead(BaseModel):
    lead_id: str
    unit_candidate_key: str
    building_name: str
    project_name: str
    area_name: str
    registry_building_name: str = ""
    registry_project_name: str = ""
    registry_area_name: str = ""
    canonical_location_id: str | None = None
    geography_match_status: str = "unmapped"
    coordinate_precision: str = "missing"
    latitude: float | None = None
    longitude: float | None = None
    asset_class: CrmAssetClass = "other"
    property_type: str
    property_subtype: str = "Property"
    matched_sales_property_type: str | None = None
    bedrooms: str
    size_sqft: float | None = None
    contract_amount_aed: int = 0
    contract_term_days: int = 0
    contract_term_months: float | None = None
    annual_rent_aed: int
    latest_purchase_price_aed: int | None = None
    unit_number: str | None = None
    unit_match_status: str = "unresolved"
    matching_units: int = 0
    last_purchase_date: date | None = None
    matched_sale_price_aed: int | None = None
    gross_yield_pct: float | None = None
    identity_sale_date: date | None = None
    identity_sale_price_aed: int | None = None
    latest_price_per_sqft_aed: float | None = None
    latest_capital_gain_pct: float | None = None
    latest_ltv_pct: float | None = None
    latest_seller_type: str | None = None
    latest_seller_transaction_count: int | None = None
    latest_market_status: str | None = None
    lease_start: date
    lease_end: date
    days_to_expiry: int
    status: LeadStatus
    priority: LeadPriority
    score: int = Field(ge=0, le=100)
    contract_state: str
    match_confidence: MatchConfidence
    property_identity_key: str = ""
    ownership_timing: str = "unit_unresolved"
    lease_evidence_state: str = "upcoming"
    data_complete_through: date | None = None
    lead_reason: str
    recommended_action: str
    sale_conversation: bool
    source: str = "Transaction registry"


class CrmBreakdownItem(BaseModel):
    label: str
    total: int
    urgent: int
    expired: int
    expiring_30: int
    expiring_60: int
    expiring_90: int
    potential_value_aed: int


class CrmFilters(BaseModel):
    areas: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    buildings: list[str] = Field(default_factory=list)
    property_types: list[str] = Field(default_factory=list)


class CrmAssetBreakdownItem(BaseModel):
    asset_class: CrmAssetClass
    total: int
    urgent: int
    exact_unit_matches: int
    annual_rent_at_risk_aed: int
    property_types: list[str] = Field(default_factory=list)


class CrmCoverage(BaseModel):
    rental_source: str
    rental_start_date: date | None = None
    rental_end_date: date | None = None
    rental_rows: int = 0
    exact_unit_ids_available: bool = False
    exact_unit_matches: int = 0
    data_complete_through: date | None = None
    matching_method: str
    caveat: str


class CrmSummary(BaseModel):
    total_leads: int
    urgent: int
    expired_unlet: int
    expiring_30_days: int
    expiring_31_to_60_days: int
    expiring_61_to_90_days: int
    sale_conversation_candidates: int
    annual_rent_at_risk_aed: int


class CrmDashboardResponse(BaseModel):
    leads: list[CrmLead]
    total: int
    limit: int
    offset: int
    summary: CrmSummary
    asset_breakdown: list[CrmAssetBreakdownItem] = Field(default_factory=list)
    breakdown: list[CrmBreakdownItem]
    breakdown_level: str
    filters: CrmFilters
    coverage: CrmCoverage
    as_of: date


class CrmTimelineEvent(BaseModel):
    event_id: str
    event_type: Literal["lease", "sale"]
    event_date: date
    title: str
    description: str
    amount_aed: int | None = None
    end_date: date | None = None
    source: str
    confidence: MatchConfidence
    ltv_pct: float | None = None
    capital_gain_pct: float | None = None


class CrmLeadDetailResponse(BaseModel):
    lead: CrmLead
    timeline: list[CrmTimelineEvent]
    next_best_actions: list[str]
    agent_signals: list[str] = Field(default_factory=list)
    match_explanation: str
    generated_at: datetime


class CrmSavedLead(SQLModel, table=True):
    __tablename__ = "crm_saved_leads"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organization_id",
            "unit_candidate_key",
            name="uq_crm_saved_lead_owner_candidate",
        ),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    user_id: str = SQLField(index=True)
    organization_id: str = SQLField(index=True)
    lead_id: str = SQLField(index=True)
    unit_candidate_key: str = SQLField(index=True)
    snapshot: dict[str, Any] = SQLField(sa_column=Column(JSON, nullable=False))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmSavedLeadResponse(BaseModel):
    id: int
    lead: CrmLead
    created_at: datetime
    updated_at: datetime


class CrmLeadWorkspace(SQLModel, table=True):
    __tablename__ = "crm_lead_workspaces"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organization_id",
            "unit_candidate_key",
            name="uq_crm_workspace_owner_candidate",
        ),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    user_id: str = SQLField(index=True)
    organization_id: str = SQLField(index=True)
    lead_id: str = SQLField(index=True)
    unit_candidate_key: str = SQLField(index=True)
    pipeline_status: str = SQLField(default="new", index=True)
    highlight_color: str = SQLField(default="none")
    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    next_follow_up: date | None = None
    tags: list[str] = SQLField(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmLeadNote(SQLModel, table=True):
    __tablename__ = "crm_lead_notes"

    id: int | None = SQLField(default=None, primary_key=True)
    workspace_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_lead_workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    user_id: str = SQLField(index=True)
    organization_id: str = SQLField(index=True)
    body: str = SQLField(sa_column=Column(Text, nullable=False))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmWorkspaceUpdate(BaseModel):
    pipeline_status: CrmPipelineStatus | None = None
    highlight_color: CrmHighlightColor | None = None
    owner_name: str | None = Field(default=None, max_length=200)
    owner_email: str | None = Field(default=None, max_length=320)
    owner_phone: str | None = Field(default=None, max_length=80)
    next_follow_up: date | None = None
    tags: list[str] | None = Field(default=None, max_length=12)


class CrmNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4_000)


class CrmLeadNoteResponse(BaseModel):
    id: int
    body: str
    created_at: datetime
    updated_at: datetime


class CrmWorkspaceSummary(BaseModel):
    id: int | None = None
    lead_id: str
    unit_candidate_key: str
    pipeline_status: CrmPipelineStatus
    highlight_color: CrmHighlightColor
    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    next_follow_up: date | None = None
    tags: list[str] = Field(default_factory=list)
    note_count: int = 0
    updated_at: datetime


class CrmWorkspaceResponse(CrmWorkspaceSummary):
    notes: list[CrmLeadNoteResponse] = Field(default_factory=list)


class CrmSaleComparable(BaseModel):
    transaction_date: date
    building_name: str
    unit_number: str
    unit_series: str | None = None
    property_type: str
    bedrooms: str
    size_sqft: float
    sale_amount_aed: int
    price_per_sqft_aed: float | None = None
    selection_reason: str


class CrmRentalComparable(BaseModel):
    lease_start: date
    building_name: str
    unit_number: str | None = None
    unit_series: str | None = None
    unit_match_status: str = "unresolved"
    property_type: str
    bedrooms: str
    size_sqft: float
    annual_rent_aed: int
    rent_per_sqft_aed: float | None = None
    selection_reason: str


class CrmReportAnalysis(BaseModel):
    estimated_market_value_aed: int | None = None
    estimated_value_low_aed: int | None = None
    estimated_value_high_aed: int | None = None
    estimated_market_rent_aed: int | None = None
    indicated_capital_change_aed: int | None = None
    indicated_capital_change_pct: float | None = None
    indicative_selling_costs_aed: int | None = None
    indicative_proceeds_before_debt_aed: int | None = None
    estimated_market_gross_yield_pct: float | None = None
    current_rent_vs_market_pct: float | None = None
    target_unit_series: str | None = None
    sales_selection_basis: str
    rental_selection_basis: str
    sales_comparables_used: int = 0
    rental_comparables_used: int = 0
    confidence: MatchConfidence


class CrmPriceIndexPoint(BaseModel):
    quarter: date
    label: str
    dubai_index: float
    dld_index: float | None = None
    transaction_index: float | None = None
    segment_index: float | None = None
    dubai_median_psf_aed: int | None = None
    segment_median_psf_aed: int | None = None
    dld_transactions: int = 0
    transaction_count: int = 0
    segment_transactions: int = 0


class CrmPriceIndex(BaseModel):
    name: str = "Vitevue Dubai Residential Price Index"
    base_period: date
    latest_period: date
    current_index: float
    change_since_base_pct: float
    year_over_year_pct: float | None = None
    current_median_psf_aed: int | None = None
    segment_name: str
    segment_current_index: float | None = None
    segment_year_over_year_pct: float | None = None
    segment_current_median_psf_aed: int | None = None
    points: list[CrmPriceIndexPoint] = Field(default_factory=list)
    methodology: str


class CrmPropertyReportResponse(BaseModel):
    lead: CrmLead
    period_start: date
    period_end: date
    sales_comparables: list[CrmSaleComparable]
    rental_comparables: list[CrmRentalComparable]
    analysis: CrmReportAnalysis
    price_index: CrmPriceIndex
    agent_signals: list[str] = Field(default_factory=list)
    methodology: list[str] = Field(default_factory=list)
    generated_at: datetime
