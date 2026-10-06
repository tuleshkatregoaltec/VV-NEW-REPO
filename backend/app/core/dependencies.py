import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.service import get_user_by_id
from app.config import settings
from app.organization.service import get_membership_for_user
from app.postgres import get_db_session
from app.providers.auth import AuthenticatedUser
from app.token_usage.service import token_usage_service

if TYPE_CHECKING:
    from app.billing.models import Subscription
    from app.organization.models import Organization, OrganizationMembership

logger = logging.getLogger(__name__)


async def require_auth(request: Request) -> AuthenticatedUser:
    """Dependency to require authentication on routes"""
    if not request.user.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return request.user


async def require_admin(request: Request) -> AuthenticatedUser:
    """Dependency to require system admin role."""
    if not request.user.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not request.user.is_admin:
        raise HTTPException(status_code=403, detail="System admin access required")

    return request.user


async def require_api_key(x_api_key: str = Header(...)) -> None:
    if not secrets.compare_digest(x_api_key, settings.SERVICE_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return None


async def require_token_quota(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(require_auth),
) -> None:
    """Dependency to check user has token quota remaining"""

    # Get today's usage
    usage = await token_usage_service.get_today_usage(db, current_user.id)
    user = await get_user_by_id(current_user.id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tokens_used = usage.total_tokens if usage else 0

    if tokens_used >= user.daily_token_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily token limit exceeded ({tokens_used}/{user.daily_token_limit} tokens used today)",
        )

    return None


@dataclass
class AuthContext:
    """Typed authentication context for protected routes"""

    user: AuthenticatedUser
    organization: "Organization"
    membership: "OrganizationMembership"
    subscription: Optional["Subscription"]


def ensure_active_subscription(context: AuthContext) -> AuthContext:
    """Enforce active/trialing billing state on an auth context."""
    if context.organization.subscription_status == "past_due":
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_PAST_DUE",
                "message": "Payment method declined. Please update your billing information.",
            },
        )

    if context.organization.subscription_status not in ["active", "trialing"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": "Active subscription required to access this resource.",
            },
        )

    return context


async def require_membership(
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """
    Require user with an organization membership.
    """
    from app.postgres.models import Organization, Subscription

    membership = await get_membership_for_user(db, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NO_ORG_MEMBERSHIP",
                "message": "You must join an organization to access this resource.",
            },
        )

    # Get organization
    organization = await db.get(Organization, membership.organization_id)
    if not organization:
        raise HTTPException(status_code=500, detail="Organization not found")

    result = await db.exec(
        select(Subscription)
        .where(Subscription.organization_id == organization.id)
        .order_by(Subscription.created_at.desc())
    )
    subscription = result.first()

    return AuthContext(
        user=current_user,
        organization=organization,
        membership=membership,
        subscription=subscription,
    )


async def require_owner_membership(
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """
    Require organization owner membership.
    """
    context = await require_membership(current_user, db)

    if context.membership.role != "owner":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "OWNER_REQUIRED",
                "message": "Organization owner access required for this action.",
            },
        )

    return context


async def require_active_subscription(
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """
    Require user with active organization subscription.

    Uses organization.subscription_status as single source of truth.
    Allows access when subscription_status in ['active', 'trialing'].
    """
    context = await require_membership(current_user, db)

    return ensure_active_subscription(context)


async def require_active_owner(
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """Require organization owner with an active subscription."""
    context = await require_owner_membership(current_user, db)

    return ensure_active_subscription(context)
