from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

CrmContactImportStatus = Literal["processing", "completed", "failed"]
CrmOwnershipStatus = Literal[
    "verified_current_owner",
    "probable_current_owner",
    "unit_linked_unverified",
    "former_owner",
    "conflicting_claim",
    "insufficient_property_data",
    "registry_not_observed",
    "unmatched",
]


class CrmContactImport(SQLModel, table=True):
    __tablename__ = "crm_contact_imports"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "sha256",
            name="uq_crm_contact_import_organization_hash",
        ),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    organization_id: str = SQLField(index=True)
    created_by_user_id: str = SQLField(index=True)
    name: str
    original_filename: str
    sha256: str = SQLField(index=True)
    size_bytes: int
    status: str = SQLField(default="processing", index=True)
    mapping: dict[str, Any] = SQLField(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    summary: dict[str, Any] = SQLField(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    error_message: str | None = SQLField(default=None, sa_column=Column(Text))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    completed_at: datetime | None = SQLField(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class CrmContactList(SQLModel, table=True):
    __tablename__ = "crm_contact_lists"

    id: int | None = SQLField(default=None, primary_key=True)
    organization_id: str = SQLField(index=True)
    created_by_user_id: str = SQLField(index=True)
    source_import_id: int | None = SQLField(
        default=None,
        sa_column=Column(
            ForeignKey("crm_contact_imports.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    name: str
    description: str | None = SQLField(default=None, sa_column=Column(Text))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmPropertyContactClaim(SQLModel, table=True):
    __tablename__ = "crm_property_contact_claims"
    __table_args__ = (
        UniqueConstraint(
            "import_id",
            "source_sheet",
            "source_row_number",
            name="uq_crm_property_contact_claim_source_row",
        ),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    organization_id: str = SQLField(index=True)
    import_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_contact_imports.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    list_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_contact_lists.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    source_sheet: str
    source_row_number: int
    row_fingerprint: str = SQLField(index=True)
    owner_key: str = SQLField(index=True)
    property_key: str = SQLField(index=True)
    contact_name: str
    phone_primary: str | None = None
    phone_alternate: str | None = None
    email_primary: str | None = None
    area_name: str = ""
    project_name: str = ""
    building_name: str = ""
    unit_number: str = ""
    property_type: str = ""
    transaction_date: date | None = None
    transaction_price_aed: int | None = None
    party_role: str = ""
    procedure_type: str = ""
    ownership_status: str = SQLField(index=True)
    confidence_score: int = 0
    match_reason: str = SQLField(sa_column=Column(Text, nullable=False))
    lead_id: str | None = SQLField(default=None, index=True)
    unit_candidate_key: str | None = SQLField(default=None, index=True)
    latest_sale_date: date | None = None
    latest_sale_price_aed: int | None = None
    later_sale_date: date | None = None
    lease_end: date | None = None
    annual_rent_aed: int | None = None
    evidence: dict[str, Any] = SQLField(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmContactImportSummary(BaseModel):
    total_rows: int = 0
    candidate_rows: int = 0
    duplicate_rows_collapsed: int = 0
    valid_contacts: int = 0
    verified_current_owners: int = 0
    probable_current_owners: int = 0
    unit_linked_unverified: int = 0
    former_owners: int = 0
    conflicting_claims: int = 0
    insufficient_property_data: int = 0
    registry_not_observed: int = 0
    unmatched: int = 0
    rental_opportunities: int = 0
    contact_ready: int = 0


class CrmSheetMapping(BaseModel):
    sheet_name: str
    header_row: int
    meaningful_rows: int
    sheet_family: str
    mapping_source: Literal["heuristic", "llm", "heuristic_fallback"]
    confidence: float = Field(ge=0, le=1)
    field_map: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CrmContactImportResponse(BaseModel):
    id: int
    list_id: int | None = None
    name: str
    original_filename: str
    status: CrmContactImportStatus
    summary: CrmContactImportSummary
    mappings: list[CrmSheetMapping] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class CrmContactImportRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CrmContactListSummary(BaseModel):
    id: int
    source_import_id: int | None = None
    name: str
    description: str | None = None
    total_contacts: int = 0
    contact_ready: int = 0
    needs_review: int = 0
    former_owners: int = 0
    created_at: datetime
    updated_at: datetime


class CrmContactClaimResponse(BaseModel):
    id: int
    source_sheet: str
    source_row_number: int
    contact_name: str
    phone_primary: str | None = None
    phone_alternate: str | None = None
    email_primary: str | None = None
    area_name: str
    project_name: str
    building_name: str
    unit_number: str
    property_type: str
    transaction_date: date | None = None
    transaction_price_aed: int | None = None
    ownership_status: CrmOwnershipStatus
    confidence_score: int
    match_reason: str
    lead_id: str | None = None
    unit_candidate_key: str | None = None
    latest_sale_date: date | None = None
    latest_sale_price_aed: int | None = None
    later_sale_date: date | None = None
    lease_end: date | None = None
    annual_rent_aed: int | None = None
    owner_key: str
    duplicate_count: int = 1
    source_rows: list[str] = Field(default_factory=list)


class CrmContactListDetail(BaseModel):
    list: CrmContactListSummary
    contacts: list[CrmContactClaimResponse]
    total: int
    limit: int
    offset: int


class CrmLeadImportedContact(BaseModel):
    claim_id: int
    list_id: int
    list_name: str
    contact_name: str
    phone_primary: str | None = None
    phone_alternate: str | None = None
    email_primary: str | None = None
    ownership_status: CrmOwnershipStatus
    confidence_score: int
    match_reason: str
    source_sheet: str
    imported_at: datetime
    owner_key: str
    duplicate_count: int = 1
    property_count: int = 1
    source_lists: list[str] = Field(default_factory=list)


class CrmOwnerProperty(BaseModel):
    property_key: str
    area_name: str
    project_name: str
    building_name: str
    unit_number: str
    property_type: str
    ownership_status: CrmOwnershipStatus
    confidence_score: int
    match_reason: str
    lead_id: str | None = None
    unit_candidate_key: str | None = None
    imported_transaction_date: date | None = None
    imported_transaction_price_aed: int | None = None
    imported_property_type: str = ""
    latest_sale_date: date | None = None
    latest_sale_price_aed: int | None = None
    registry_sale_date: date | None = None
    registry_sale_price_aed: int | None = None
    registry_property_type: str | None = None
    registry_bedrooms: str | None = None
    registry_size_sqft: float | None = None
    registry_built_up_area_sqft: float | None = None
    registry_price_per_sqft_aed: float | None = None
    registry_market_status: str | None = None
    later_sale_date: date | None = None
    lease_end: date | None = None
    annual_rent_aed: int | None = None
    duplicate_count: int = 1
    source_lists: list[str] = Field(default_factory=list)
    source_rows: list[str] = Field(default_factory=list)


class CrmOwnerProfile(BaseModel):
    owner_key: str
    contact_name: str
    phone_primary: str | None = None
    phone_alternate: str | None = None
    email_primary: str | None = None
    highest_ownership_status: CrmOwnershipStatus
    highest_confidence_score: int
    property_count: int
    rental_linked_count: int
    contact_ready_count: int
    annual_rent_aed: int
    next_lease_end: date | None = None
    properties: list[CrmOwnerProperty] = Field(default_factory=list)


class CrmOwnerRegistrySummary(BaseModel):
    rental_owner_profiles: int = 0
    registry_owner_profiles: int = 0
    prior_owner_profiles: int = 0
    needs_review_profiles: int = 0
    multi_property_owners: int = 0


class CrmOwnerRegistryResponse(BaseModel):
    scope: Literal["all", "rental_ready", "registry", "prior_owners"]
    owners: list[CrmOwnerProfile]
    total: int
    limit: int
    offset: int
    summary: CrmOwnerRegistrySummary


class CrmOwnerWorkspace(SQLModel, table=True):
    __tablename__ = "crm_owner_workspaces"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organization_id",
            "owner_key",
            name="uq_crm_owner_workspace_identity",
        ),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    user_id: str = SQLField(index=True)
    organization_id: str = SQLField(index=True)
    owner_key: str = SQLField(index=True)
    pipeline_status: str = SQLField(default="new", index=True)
    highlight_color: str = SQLField(default="none")
    next_follow_up: date | None = None
    tags: list[str] = SQLField(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmOwnerNote(SQLModel, table=True):
    __tablename__ = "crm_owner_notes"

    id: int | None = SQLField(default=None, primary_key=True)
    workspace_id: int = SQLField(
        sa_column=Column(
            ForeignKey("crm_owner_workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    user_id: str = SQLField(index=True)
    organization_id: str = SQLField(index=True)
    body: str = SQLField(sa_column=Column(Text, nullable=False))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class CrmOwnerWorkspaceSummary(BaseModel):
    owner_key: str
    pipeline_status: Literal[
        "new",
        "researching",
        "contact_ready",
        "contacted",
        "qualified",
        "nurture",
        "won",
        "closed",
    ]
    highlight_color: Literal["none", "amber", "green", "blue", "red", "purple"]
    next_follow_up: date | None = None
    tags: list[str] = Field(default_factory=list)
    note_count: int = 0
    last_note: str | None = None
    updated_at: datetime


class CrmOwnerBulkUpdate(BaseModel):
    owner_keys: list[str] = Field(min_length=1, max_length=200)
    pipeline_status: Literal[
        "new",
        "researching",
        "contact_ready",
        "contacted",
        "qualified",
        "nurture",
        "won",
        "closed",
    ] | None = None
    highlight_color: Literal["none", "amber", "green", "blue", "red", "purple"] | None = None
    note: str | None = Field(default=None, max_length=4_000)
