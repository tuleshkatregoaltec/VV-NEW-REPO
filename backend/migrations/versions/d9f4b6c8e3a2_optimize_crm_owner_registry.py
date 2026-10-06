"""optimize CRM owner registry ranking

Revision ID: d9f4b6c8e3a2
Revises: c8e3a5b7d2f1
Create Date: 2026-07-30 14:05:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d9f4b6c8e3a2"
down_revision: Union[str, Sequence[str], None] = "c8e3a5b7d2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PREFERENCE_EXPRESSION = """
(
    CASE ownership_status
        WHEN 'former_owner' THEN 6
        WHEN 'verified_current_owner' THEN 5
        WHEN 'probable_current_owner' THEN 4
        WHEN 'unit_linked_unverified' THEN 3
        WHEN 'conflicting_claim' THEN 2
        ELSE 1
    END
)
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_crm_claim_owner_property_preference
        ON crm_property_contact_claims (
            organization_id,
            owner_key,
            property_key,
            {_PREFERENCE_EXPRESSION} DESC,
            confidence_score DESC,
            transaction_date DESC NULLS LAST
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_crm_claim_list_owner_property_preference
        ON crm_property_contact_claims (
            organization_id,
            list_id,
            owner_key,
            property_key,
            {_PREFERENCE_EXPRESSION} DESC,
            confidence_score DESC,
            transaction_date DESC NULLS LAST
        )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_crm_claim_list_owner_property_preference",
        table_name="crm_property_contact_claims",
    )
    op.drop_index(
        "ix_crm_claim_owner_property_preference",
        table_name="crm_property_contact_claims",
    )
