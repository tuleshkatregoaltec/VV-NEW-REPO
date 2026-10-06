"""add CRM inbound contacts, enquiries, imports, notes, and matches

Revision ID: e1a7c9d3f5b2
Revises: d9f4b6c8e3a2
Create Date: 2026-08-03 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "e1a7c9d3f5b2"
down_revision: Union[str, Sequence[str], None] = "d9f4b6c8e3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column], unique=False)


def upgrade() -> None:
    string = sqlmodel.sql.sqltypes.AutoString
    op.create_table(
        "crm_inbound_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", string(), nullable=False),
        sa.Column("created_by_user_id", string(), nullable=False),
        sa.Column("name", string(), nullable=False),
        sa.Column("original_filename", string(), nullable=False),
        sa.Column("sha256", string(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", string(), nullable=False, server_default="processing"),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "sha256", name="uq_crm_inbound_import_org_hash"),
    )
    _indexes("crm_inbound_imports", ("organization_id", "created_by_user_id", "sha256", "status"))

    op.create_table(
        "crm_inbound_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", string(), nullable=False),
        sa.Column("full_name", string(), nullable=False),
        sa.Column("phone", string(), nullable=True),
        sa.Column("email", string(), nullable=True),
        sa.Column("whatsapp", string(), nullable=True),
        sa.Column("preferred_language", string(), nullable=True),
        sa.Column("preferred_channel", string(), nullable=True),
        sa.Column("consent_status", string(), nullable=False, server_default="unknown"),
        sa.Column("do_not_contact", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("crm_inbound_contacts", ("organization_id", "phone", "email", "consent_status", "do_not_contact"))

    op.create_table(
        "crm_inbound_enquiries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", string(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("source_import_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", string(), nullable=False),
        sa.Column("assigned_user_id", string(), nullable=True),
        sa.Column("intent", string(), nullable=False),
        sa.Column("status", string(), nullable=False, server_default="new"),
        sa.Column("source", string(), nullable=False, server_default="Manual"),
        sa.Column("campaign", string(), nullable=True),
        sa.Column("source_lead_id", string(), nullable=True),
        sa.Column("source_sheet", string(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("enquiry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("strict_fields", sa.JSON(), nullable=False),
        sa.Column("raw_notes", sa.Text(), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("extraction_evidence", sa.JSON(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("next_follow_up", sa.Date(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["crm_inbound_contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_import_id"], ["crm_inbound_imports.id"], ondelete="SET NULL"),
    )
    _indexes("crm_inbound_enquiries", ("organization_id", "contact_id", "source_import_id", "created_by_user_id", "assigned_user_id", "intent", "status", "source", "campaign", "source_lead_id"))

    op.create_table(
        "crm_inbound_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enquiry_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", string(), nullable=False),
        sa.Column("user_id", string(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enquiry_id"], ["crm_inbound_enquiries.id"], ondelete="CASCADE"),
    )
    _indexes("crm_inbound_notes", ("enquiry_id", "organization_id", "user_id"))

    op.create_table(
        "crm_inbound_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enquiry_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", string(), nullable=False),
        sa.Column("target_type", string(), nullable=False),
        sa.Column("target_key", string(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("state", string(), nullable=False, server_default="suggested"),
        sa.Column("title", string(), nullable=False),
        sa.Column("subtitle", string(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", string(), nullable=False, server_default="inbound-v1"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enquiry_id"], ["crm_inbound_enquiries.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("enquiry_id", "target_type", "target_key", name="uq_crm_inbound_match_target"),
    )
    _indexes("crm_inbound_matches", ("enquiry_id", "organization_id", "target_type", "target_key", "score", "state"))


def downgrade() -> None:
    op.drop_table("crm_inbound_matches")
    op.drop_table("crm_inbound_notes")
    op.drop_table("crm_inbound_enquiries")
    op.drop_table("crm_inbound_contacts")
    op.drop_table("crm_inbound_imports")
