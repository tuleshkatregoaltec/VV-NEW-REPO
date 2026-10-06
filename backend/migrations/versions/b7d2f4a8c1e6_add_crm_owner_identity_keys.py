"""add CRM owner and property identity keys

Revision ID: b7d2f4a8c1e6
Revises: a9c4e1f7b2d8
Create Date: 2026-07-29 22:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2f4a8c1e6"
down_revision: Union[str, Sequence[str], None] = "a9c4e1f7b2d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crm_property_contact_claims",
        sa.Column("owner_key", sa.String(), nullable=True),
    )
    op.add_column(
        "crm_property_contact_claims",
        sa.Column("property_key", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE crm_property_contact_claims
        SET
            property_key =
                lower(
                    regexp_replace(
                        coalesce(nullif(building_name, ''), project_name),
                        '[^a-z0-9]',
                        '',
                        'g'
                    )
                ) || '|' || lower(unit_number),
            owner_key = md5(
                lower(regexp_replace(contact_name, '[^[:alnum:]]', '', 'g'))
                || '|'
                || coalesce(
                    phone_primary,
                    phone_alternate,
                    lower(email_primary),
                    lower(coalesce(nullif(building_name, ''), project_name))
                        || '|' || lower(unit_number)
                )
            )
        """
    )
    op.alter_column(
        "crm_property_contact_claims",
        "owner_key",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        "crm_property_contact_claims",
        "property_key",
        existing_type=sa.String(),
        nullable=False,
    )
    op.create_index(
        "ix_crm_claim_org_owner",
        "crm_property_contact_claims",
        ["organization_id", "owner_key"],
        unique=False,
    )
    op.create_index(
        "ix_crm_claim_org_owner_property",
        "crm_property_contact_claims",
        ["organization_id", "owner_key", "property_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_crm_claim_org_owner_property",
        table_name="crm_property_contact_claims",
    )
    op.drop_index(
        "ix_crm_claim_org_owner",
        table_name="crm_property_contact_claims",
    )
    op.drop_column("crm_property_contact_claims", "property_key")
    op.drop_column("crm_property_contact_claims", "owner_key")
