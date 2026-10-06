"""add CRM contact imports and lists

Revision ID: a9c4e1f7b2d8
Revises: 7b8c9d0e1f23
Create Date: 2026-07-29 21:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "a9c4e1f7b2d8"
down_revision: Union[str, Sequence[str], None] = "7b8c9d0e1f23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_contact_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_by_user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("original_filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sha256", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="processing",
        ),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "sha256",
            name="uq_crm_contact_import_organization_hash",
        ),
    )
    for column in ("organization_id", "created_by_user_id", "sha256", "status"):
        op.create_index(
            op.f(f"ix_crm_contact_imports_{column}"),
            "crm_contact_imports",
            [column],
            unique=False,
        )

    op.create_table(
        "crm_contact_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_by_user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_import_id", sa.Integer(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_import_id"],
            ["crm_contact_imports.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "created_by_user_id", "source_import_id"):
        op.create_index(
            op.f(f"ix_crm_contact_lists_{column}"),
            "crm_contact_lists",
            [column],
            unique=False,
        )

    op.create_table(
        "crm_property_contact_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("source_sheet", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("row_fingerprint", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("contact_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("phone_primary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("phone_alternate", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("email_primary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("area_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("building_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unit_number", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("property_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("transaction_price_aed", sa.BigInteger(), nullable=True),
        sa.Column("party_role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("procedure_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ownership_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("lead_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("unit_candidate_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("latest_sale_date", sa.Date(), nullable=True),
        sa.Column("latest_sale_price_aed", sa.BigInteger(), nullable=True),
        sa.Column("later_sale_date", sa.Date(), nullable=True),
        sa.Column("lease_end", sa.Date(), nullable=True),
        sa.Column("annual_rent_aed", sa.BigInteger(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["crm_contact_imports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["crm_contact_lists.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_id",
            "source_sheet",
            "source_row_number",
            name="uq_crm_property_contact_claim_source_row",
        ),
    )
    for column in (
        "organization_id",
        "import_id",
        "list_id",
        "row_fingerprint",
        "ownership_status",
        "lead_id",
        "unit_candidate_key",
    ):
        op.create_index(
            op.f(f"ix_crm_property_contact_claims_{column}"),
            "crm_property_contact_claims",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "unit_candidate_key",
        "lead_id",
        "ownership_status",
        "row_fingerprint",
        "list_id",
        "import_id",
        "organization_id",
    ):
        op.drop_index(
            op.f(f"ix_crm_property_contact_claims_{column}"),
            table_name="crm_property_contact_claims",
        )
    op.drop_table("crm_property_contact_claims")
    for column in ("source_import_id", "created_by_user_id", "organization_id"):
        op.drop_index(
            op.f(f"ix_crm_contact_lists_{column}"),
            table_name="crm_contact_lists",
        )
    op.drop_table("crm_contact_lists")
    for column in ("status", "sha256", "created_by_user_id", "organization_id"):
        op.drop_index(
            op.f(f"ix_crm_contact_imports_{column}"),
            table_name="crm_contact_imports",
        )
    op.drop_table("crm_contact_imports")
