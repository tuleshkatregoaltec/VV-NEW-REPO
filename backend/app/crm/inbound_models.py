from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

InboundIntent = Literal["unknown", "buy", "rent", "sell", "let"]
InboundRecordKind = Literal["unqualified_contact", "opportunity"]
InboundStatus = Literal[
    "new",
    "needs_review",
    "assigned",
    "attempted",
    "contacted",
    "qualified",
    "viewing",
    "valuation",
    "signed",
    "active",
    "won",
    "nurture",
    "closed_lost",
    "disqualified",
]
InboundMatchState = Literal["suggested", "saved", "dismissed", "contacted", "stale"]


class CrmInboundImport(SQLModel, table=True):
    __tablename__ = "crm_inbound_imports"
    __table_args__ = (
        UniqueConstraint("organization_id", "sha256", name="uq_crm_inbound_import_org_hash"),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    organization_id: str = SQLField(index=True)
    created_by_user_id: str = SQLField(index=True)
    name: str
    original_filename: str
    sha256: str = SQLField(index=True)
    size_bytes: int
    status: str = SQLField(default="processing", index=True)
    mapping: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON, nullable=False))
    summary: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error_message: str | None = SQLField(default=None, sa_column=Column(Text))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    completed_at: datetime | None = SQLField(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class CrmInboundContact(SQLModel, table=True):
    __tablename__ = "crm_inbound_contacts"

    id: int | None = SQLField(default=None, primary_key=True)
    organization_id: str = SQLField(index=True)
    full_name: str
    phone: str | None = SQLField(default=None, index=True)
    email: str | None = SQLField(default=None, index=True)
    whatsapp: str | None = None
    preferred_language: str | None = None
    preferred_channel: str | None = None
    consent_status: str = SQLField(default="unknown", index=True)
    do_not_contact: bool = SQLField(default=False, index=True)
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmInboundEnquiry(SQLModel, table=True):
    __tablename__ = "crm_inbound_enquiries"

    id: int | None = SQLField(default=None, primary_key=True)
    organization_id: str = SQLField(index=True)
    contact_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_inbound_contacts.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    source_import_id: int | None = SQLField(
        default=None,
        sa_column=Column(
            ForeignKey("crm_inbound_imports.id", ondelete="SET NULL"), nullable=True, index=True
        ),
    )
    created_by_user_id: str = SQLField(index=True)
    assigned_user_id: str | None = SQLField(default=None, index=True)
    record_kind: str = SQLField(default="unqualified_contact", index=True)
    intent: str = SQLField(index=True)
    status: str = SQLField(default="new", index=True)
    source: str = SQLField(default="Manual", index=True)
    campaign: str | None = SQLField(default=None, index=True)
    source_lead_id: str | None = SQLField(default=None, index=True)
    source_sheet: str | None = None
    source_row_number: int | None = None
    enquiry_date: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    criteria: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    strict_fields: list[str] = SQLField(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    raw_notes: str | None = SQLField(default=None, sa_column=Column(Text))
    observed_data: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    inferred_data: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    confirmed_data: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    qualification: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    extraction_confidence: float = 1.0
    extraction_evidence: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    review_reasons: list[str] = SQLField(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    next_follow_up: date | None = None
    first_response_due_at: datetime | None = SQLField(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    first_contact_at: datetime | None = SQLField(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_contact_at: datetime | None = SQLField(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    contact_attempt_count: int = 0
    lost_reason: str | None = None
    tags: list[str] = SQLField(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmInboundNote(SQLModel, table=True):
    __tablename__ = "crm_inbound_notes"

    id: int | None = SQLField(default=None, primary_key=True)
    enquiry_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_inbound_enquiries.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    organization_id: str = SQLField(index=True)
    user_id: str = SQLField(index=True)
    body: str = SQLField(sa_column=Column(Text, nullable=False))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmInboundActivity(SQLModel, table=True):
    __tablename__ = "crm_inbound_activities"

    id: int | None = SQLField(default=None, primary_key=True)
    enquiry_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_inbound_enquiries.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    organization_id: str = SQLField(index=True)
    user_id: str = SQLField(index=True)
    activity_type: str = SQLField(index=True)
    body: str | None = SQLField(default=None, sa_column=Column(Text))
    metadata_json: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmInboundMatch(SQLModel, table=True):
    __tablename__ = "crm_inbound_matches"
    __table_args__ = (
        UniqueConstraint(
            "enquiry_id", "target_type", "target_key", name="uq_crm_inbound_match_target"
        ),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    enquiry_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_inbound_enquiries.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    organization_id: str = SQLField(index=True)
    target_type: str = SQLField(index=True)
    target_key: str = SQLField(index=True)
    score: int = SQLField(index=True)
    state: str = SQLField(default="suggested", index=True)
    title: str
    subtitle: str
    reasons: list[str] = SQLField(default_factory=list, sa_column=Column(JSON, nullable=False))
    score_breakdown: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    fit: str = SQLField(default="review", index=True)
    missing_fields: list[str] = SQLField(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    snapshot: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    algorithm_version: str = "inbound-v1"
    generated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class InboundImportSummary(BaseModel):
    total_rows: int = 0
    imported: int = 0
    duplicates: int = 0
    needs_review: int = 0
    buyers: int = 0
    tenants: int = 0
    sellers: int = 0
    landlords: int = 0
    unqualified_contacts: int = 0
    rejected: int = 0
    owner_matches: int = 0
    current_owners: int = 0
    former_owners: int = 0
    rental_owners: int = 0
    portfolio_owners: int = 0
    high_priority: int = 0


class InboundImportResponse(BaseModel):
    id: int
    name: str
    original_filename: str
    status: Literal["processing", "completed", "failed"]
    summary: InboundImportSummary
    mapping: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class InboundRegistryProfileResponse(BaseModel):
    owner_key: str
    contact_name: str
    ownership_status: str
    identity_strength: Literal["exact", "possible", "weak"]
    identity_reason: str
    area_name: str
    project_name: str
    building_name: str
    unit_number: str
    property_type: str
    transaction_date: date | None = None
    transaction_price_aed: int | None = None
    latest_sale_date: date | None = None
    latest_sale_price_aed: int | None = None
    later_sale_date: date | None = None
    ltv_pct: float | None = None
    seller_type: str | None = None
    lease_start: date | None = None
    lease_end: date | None = None
    annual_rent_aed: int | None = None
    contract_state: str | None = None
    lead_id: str | None = None


class InboundContactResponse(BaseModel):
    id: int
    full_name: str
    phone: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    preferred_language: str | None = None
    preferred_channel: str | None = None
    consent_status: str
    do_not_contact: bool
    registry_profiles: list[InboundRegistryProfileResponse] = Field(default_factory=list)


class InboundEnquiryCreate(BaseModel):
    intent: InboundIntent = "unknown"
    record_kind: InboundRecordKind = "unqualified_contact"
    full_name: str = Field(min_length=1, max_length=240)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=320)
    whatsapp: str | None = Field(default=None, max_length=80)
    source: str = Field(default="Manual", max_length=120)
    campaign: str | None = Field(default=None, max_length=200)
    assigned_user_id: str | None = None
    notes: str | None = Field(default=None, max_length=8_000)
    criteria: dict[str, Any] = Field(default_factory=dict)
    strict_fields: list[str] = Field(default_factory=list, max_length=20)
    consent_status: str = "unknown"


class InboundEnquiryUpdate(BaseModel):
    intent: InboundIntent | None = None
    status: InboundStatus | None = None
    record_kind: InboundRecordKind | None = None
    assigned_user_id: str | None = None
    criteria: dict[str, Any] | None = None
    strict_fields: list[str] | None = Field(default=None, max_length=20)
    next_follow_up: date | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=8_000)
    confirmed_data: dict[str, Any] | None = None
    qualification: dict[str, Any] | None = None
    lost_reason: str | None = Field(default=None, max_length=500)
    consent_status: Literal["unknown", "provided", "withdrawn"] | None = None
    do_not_contact: bool | None = None
    preferred_channel: str | None = Field(default=None, max_length=40)


class InboundNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4_000)


class InboundNoteResponse(BaseModel):
    id: int
    body: str
    user_id: str
    created_at: datetime


class InboundActivityCreate(BaseModel):
    activity_type: Literal["contact_attempt", "call", "email", "whatsapp", "meeting"]
    body: str | None = Field(default=None, max_length=4_000)


class InboundActivityResponse(BaseModel):
    id: int
    activity_type: str
    body: str | None = None
    user_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class InboundOwnershipEnrichmentResponse(BaseModel):
    matched: bool = False
    match_basis: Literal["phone", "email", "name", "none"] = "none"
    verification: Literal["contact_exact", "name_only", "none"] = "none"
    current_owner: bool = False
    former_owner: bool = False
    rental_owner: bool = False
    multiple_property_owner: bool = False
    current_property_count: int = 0
    prior_property_count: int = 0
    rental_property_count: int = 0
    known_property_count: int = 0
    observed_portfolio_value_aed: int = 0
    reasons: list[str] = Field(default_factory=list)


class InboundPriorityResponse(BaseModel):
    band: Literal["high", "medium", "standard"] = "standard"
    score: int = Field(default=0, ge=0, le=100)
    opportunity_value_aed: int = 0
    reasons: list[str] = Field(default_factory=list)


class InboundEnquiryResponse(BaseModel):
    id: int
    contact: InboundContactResponse
    record_kind: InboundRecordKind
    intent: InboundIntent
    status: InboundStatus
    assigned_user_id: str | None = None
    source: str
    campaign: str | None = None
    source_import_id: int | None = None
    enquiry_date: datetime
    criteria: dict[str, Any]
    strict_fields: list[str]
    raw_notes: str | None = None
    observed_data: dict[str, Any]
    inferred_data: dict[str, Any]
    confirmed_data: dict[str, Any]
    qualification: dict[str, Any]
    extraction_confidence: float
    review_reasons: list[str]
    next_follow_up: date | None = None
    first_response_due_at: datetime | None = None
    first_contact_at: datetime | None = None
    last_contact_at: datetime | None = None
    contact_attempt_count: int = 0
    lost_reason: str | None = None
    sla_state: Literal["on_time", "due_soon", "overdue", "responded"]
    qualification_complete: bool
    ownership_enrichment: InboundOwnershipEnrichmentResponse = Field(
        default_factory=InboundOwnershipEnrichmentResponse
    )
    priority: InboundPriorityResponse = Field(default_factory=InboundPriorityResponse)
    tags: list[str]
    notes: list[InboundNoteResponse] = Field(default_factory=list)
    activities: list[InboundActivityResponse] = Field(default_factory=list)
    match_count: int = 0
    saved_match_count: int = 0
    created_at: datetime
    updated_at: datetime


class InboundEnquiryListResponse(BaseModel):
    enquiries: list[InboundEnquiryResponse]
    total: int
    summary: dict[str, int]


class InboundMatchResponse(BaseModel):
    id: int
    target_type: Literal["owner", "unit", "listing", "project", "demand"]
    target_key: str
    state: InboundMatchState
    fit: Literal["exact", "near", "review", "outside"]
    title: str
    subtitle: str
    reasons: list[str]
    missing_fields: list[str]
    snapshot: dict[str, Any]
    generated_at: datetime


class InboundMatchesResponse(BaseModel):
    enquiry_id: int
    listing_fresh: bool
    listing_last_refresh: datetime | None = None
    offplan_catalog_available: bool = False
    offplan_last_refresh: datetime | None = None
    lanes: dict[str, list[InboundMatchResponse]]


class InboundMatchUpdate(BaseModel):
    state: InboundMatchState


class InboundImportPreviewSheet(BaseModel):
    sheet: str
    header_row: int
    headers: list[str]
    field_map: dict[str, str]
    sample_rows: list[dict[str, str]] = Field(default_factory=list)
    row_count: int = 0
    mapping_source: Literal["deterministic", "ai_assisted"] = "deterministic"


class InboundImportPreviewResponse(BaseModel):
    original_filename: str
    size_bytes: int
    total_rows: int
    sheets: list[InboundImportPreviewSheet]
    warnings: list[str] = Field(default_factory=list)
