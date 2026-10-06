"""add feasibility study chat state column

Revision ID: 9f1c6a2d4e7b
Revises: 2c7f2f6b9d51
Create Date: 2026-05-03 14:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f1c6a2d4e7b"
down_revision: Union[str, Sequence[str], None] = "2c7f2f6b9d51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column("feasibility_studies", "chat_state"):
        return

    op.add_column(
        "feasibility_studies",
        sa.Column(
            "chat_state",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("""'{"messages": [], "history_json": null}'::json"""),
        ),
    )
    op.alter_column("feasibility_studies", "chat_state", server_default=None)


def downgrade() -> None:
    # No-op: fresh databases already get this column from the create-table migration.
    pass
