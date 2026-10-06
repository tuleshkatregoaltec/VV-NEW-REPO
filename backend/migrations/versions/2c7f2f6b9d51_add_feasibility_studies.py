"""add feasibility studies

Revision ID: 2c7f2f6b9d51
Revises: 8395bd1f2518
Create Date: 2026-05-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "2c7f2f6b9d51"
down_revision: Union[str, Sequence[str], None] = "8395bd1f2518"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feasibility_studies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("plot_number", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("development_model", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("plot_data", sa.JSON(), nullable=False),
        sa.Column("research", sa.JSON(), nullable=False),
        sa.Column("study_context", sa.JSON(), nullable=False),
        sa.Column("chat_state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_feasibility_studies_organization_id"),
        "feasibility_studies",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feasibility_studies_plot_number"),
        "feasibility_studies",
        ["plot_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feasibility_studies_user_id"),
        "feasibility_studies",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_feasibility_studies_owner_updated",
        "feasibility_studies",
        ["user_id", "organization_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_feasibility_studies_owner_updated", table_name="feasibility_studies")
    op.drop_index(op.f("ix_feasibility_studies_user_id"), table_name="feasibility_studies")
    op.drop_index(op.f("ix_feasibility_studies_plot_number"), table_name="feasibility_studies")
    op.drop_index(
        op.f("ix_feasibility_studies_organization_id"),
        table_name="feasibility_studies",
    )
    op.drop_table("feasibility_studies")
