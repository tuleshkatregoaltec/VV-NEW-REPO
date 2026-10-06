"""add CRM owner workspaces and notes

Revision ID: c8e3a5b7d2f1
Revises: b7d2f4a8c1e6
Create Date: 2026-07-30 11:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "c8e3a5b7d2f1"
down_revision: Union[str, Sequence[str], None] = "b7d2f4a8c1e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_owner_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("owner_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
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
        sa.Column("next_follow_up", sa.Date(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "organization_id",
            "owner_key",
            name="uq_crm_owner_workspace_identity",
        ),
    )
    for column in ("user_id", "organization_id", "owner_key", "pipeline_status"):
        op.create_index(
            op.f(f"ix_crm_owner_workspaces_{column}"),
            "crm_owner_workspaces",
            [column],
            unique=False,
        )

    op.create_table(
        "crm_owner_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["crm_owner_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "user_id", "organization_id"):
        op.create_index(
            op.f(f"ix_crm_owner_notes_{column}"),
            "crm_owner_notes",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("organization_id", "user_id", "workspace_id"):
        op.drop_index(
            op.f(f"ix_crm_owner_notes_{column}"),
            table_name="crm_owner_notes",
        )
    op.drop_table("crm_owner_notes")
    for column in ("pipeline_status", "owner_key", "organization_id", "user_id"):
        op.drop_index(
            op.f(f"ix_crm_owner_workspaces_{column}"),
            table_name="crm_owner_workspaces",
        )
    op.drop_table("crm_owner_workspaces")
