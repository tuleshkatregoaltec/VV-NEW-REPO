"""add CRM lead workspaces and notes

Revision ID: 7b8c9d0e1f23
Revises: 4d7f6a8b9c10
Create Date: 2026-07-29 00:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "7b8c9d0e1f23"
down_revision: Union[str, Sequence[str], None] = "4d7f6a8b9c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_lead_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lead_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unit_candidate_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "pipeline_status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "highlight_color",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="none",
        ),
        sa.Column("owner_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("owner_email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("owner_phone", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("next_follow_up", sa.Date(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "organization_id",
            "unit_candidate_key",
            name="uq_crm_workspace_owner_candidate",
        ),
    )
    for column in (
        "user_id",
        "organization_id",
        "lead_id",
        "unit_candidate_key",
        "pipeline_status",
    ):
        op.create_index(
            op.f(f"ix_crm_lead_workspaces_{column}"),
            "crm_lead_workspaces",
            [column],
            unique=False,
        )

    op.create_table(
        "crm_lead_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["crm_lead_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "user_id", "organization_id"):
        op.create_index(
            op.f(f"ix_crm_lead_notes_{column}"),
            "crm_lead_notes",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("organization_id", "user_id", "workspace_id"):
        op.drop_index(
            op.f(f"ix_crm_lead_notes_{column}"),
            table_name="crm_lead_notes",
        )
    op.drop_table("crm_lead_notes")
    for column in (
        "pipeline_status",
        "unit_candidate_key",
        "lead_id",
        "organization_id",
        "user_id",
    ):
        op.drop_index(
            op.f(f"ix_crm_lead_workspaces_{column}"),
            table_name="crm_lead_workspaces",
        )
    op.drop_table("crm_lead_workspaces")
