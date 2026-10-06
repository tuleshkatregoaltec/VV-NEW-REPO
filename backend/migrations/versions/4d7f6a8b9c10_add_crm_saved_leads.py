"""add CRM saved leads

Revision ID: 4d7f6a8b9c10
Revises: 9f1c6a2d4e7b
Create Date: 2026-07-28 21:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "4d7f6a8b9c10"
down_revision: Union[str, Sequence[str], None] = "9f1c6a2d4e7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_saved_leads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lead_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unit_candidate_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "organization_id",
            "unit_candidate_key",
            name="uq_crm_saved_lead_owner_candidate",
        ),
    )
    op.create_index(
        op.f("ix_crm_saved_leads_user_id"),
        "crm_saved_leads",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_saved_leads_organization_id"),
        "crm_saved_leads",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_saved_leads_lead_id"),
        "crm_saved_leads",
        ["lead_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_saved_leads_unit_candidate_key"),
        "crm_saved_leads",
        ["unit_candidate_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_crm_saved_leads_unit_candidate_key"),
        table_name="crm_saved_leads",
    )
    op.drop_index(op.f("ix_crm_saved_leads_lead_id"), table_name="crm_saved_leads")
    op.drop_index(
        op.f("ix_crm_saved_leads_organization_id"),
        table_name="crm_saved_leads",
    )
    op.drop_index(op.f("ix_crm_saved_leads_user_id"), table_name="crm_saved_leads")
    op.drop_table("crm_saved_leads")
