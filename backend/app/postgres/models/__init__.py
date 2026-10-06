"""PostgreSQL models for application state (not analytics data).

This module re-exports SQLModel classes from their feature modules so Alembic
and any code importing from `app.postgres.models` continue to work during the
migration.
"""

from app.billing.models import Subscription
from app.chat.models import Conversation, Message
from app.crm.import_models import (
    CrmContactImport,
    CrmContactList,
    CrmOwnerNote,
    CrmOwnerWorkspace,
    CrmPropertyContactClaim,
)
from app.crm.inbound_models import (
    CrmInboundContact,
    CrmInboundEnquiry,
    CrmInboundImport,
    CrmInboundMatch,
    CrmInboundNote,
)
from app.crm.models import CrmLeadNote, CrmLeadWorkspace, CrmSavedLead
from app.feasibility.models import FeasibilitySavedStudy
from app.news.models import NewsArticle
from app.organization.models import Organization
from app.token_usage.models import UserTokenUsage

__all__ = [
    # Auth & User Management
    "Organization",
    "UserTokenUsage",
    # Billing
    "Subscription",
    # News
    "NewsArticle",
    # Chat
    "Conversation",
    "Message",
    # CRM
    "CrmSavedLead",
    "CrmLeadWorkspace",
    "CrmLeadNote",
    "CrmContactImport",
    "CrmContactList",
    "CrmPropertyContactClaim",
    "CrmOwnerWorkspace",
    "CrmOwnerNote",
    "CrmInboundImport",
    "CrmInboundContact",
    "CrmInboundEnquiry",
    "CrmInboundNote",
    "CrmInboundMatch",
    # Feasibility
    "FeasibilitySavedStudy",
]
