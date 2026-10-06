import logging
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import (
    CreateUserRequest,
    CreateUserResponse,
    OrganizationListResponse,
    OrganizationMemberResponse,
    OrgDetailResponse,
    OrgUserResponse,
    UpdateOrgRequest,
    UpdateSubscriptionRequest,
    UpdateUserRequest,
    UserDetailResponse,
)
from app.auth.service import (
    create_user_admin,
    delete_user_admin,
    get_user_by_id,
    update_user_token_limit,
)
from app.billing.models import Subscription
from app.core.dependencies import require_admin
from app.organization.models import Organization, OrganizationMembership
from app.organization.service import (
    add_user_to_organization,
    create_organization,
    delete_organization,
    get_membership_for_user,
    get_owner_membership_for_org,
    remove_user_from_organization,
    update_organization,
    update_subscription_status,
)
from app.postgres import get_db_session
from app.token_usage.models import UserTokenStatsResponse, UserTokenUsage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


async def get_owner_email(db: AsyncSession, org_id: str) -> str:
    owner_membership = await get_owner_membership_for_org(db, org_id)
    if not owner_membership:
        return "unknown"

    owner = await get_user_by_id(owner_membership.user_id)
    return owner.email if owner else "unknown"


# ─── Organizations ────────────────────────────────────────────────────────────


@router.get("/organizations", response_model=List[OrganizationListResponse])
async def list_all_organizations(db: AsyncSession = Depends(get_db_session)):
    """List all organizations with stats."""
    orgs_result = await db.execute(select(Organization))
    organizations = orgs_result.scalars().all()

    response = []
    for org in organizations:
        members_result = await db.execute(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == org.id
            )
        )
        user_count = members_result.scalar() or 0

        sub_result = await db.execute(
            select(Subscription).where(Subscription.organization_id == org.id)
        )
        subscription = sub_result.scalar_one_or_none()

        owner_email = await get_owner_email(db, org.id)

        response.append(
            OrganizationListResponse(
                id=org.id,
                name=org.name,
                owner_email=owner_email,
                user_count=user_count,
                max_users=org.max_users,
                subscription_status=org.subscription_status,
                seats=subscription.seats if subscription else 0,
                created_at=org.created_at,
            )
        )

    return response


@router.get("/organizations/{org_id}", response_model=OrgDetailResponse)
async def get_organization(org_id: str, db: AsyncSession = Depends(get_db_session)):
    """Get organization details with members."""
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    memberships_result = await db.execute(
        select(OrganizationMembership).where(OrganizationMembership.organization_id == org_id)
    )
    memberships = memberships_result.scalars().all()

    # Fetch today's token usage for all members in one query
    today = date.today()
    user_ids = [m.user_id for m in memberships]
    usage_by_user = {}
    if user_ids:
        usage_result = await db.execute(
            select(UserTokenUsage).where(
                UserTokenUsage.user_id.in_(user_ids),
                UserTokenUsage.date == today,
            )
        )
        usage_by_user = {u.user_id: u for u in usage_result.scalars().all()}

    users = []
    for membership in memberships:
        user = await get_user_by_id(membership.user_id)
        if not user:
            continue
        usage = usage_by_user.get(membership.user_id)
        tokens_used = usage.total_tokens if usage else 0
        limit = user.daily_token_limit or 0
        pct = (tokens_used / limit * 100) if limit > 0 else 0.0

        users.append(
            OrgUserResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                role=membership.role,
                daily_token_limit=limit,
                tokens_used_today=tokens_used,
                usage_percentage=round(pct, 1),
                last_login=user.last_login_at,
            )
        )

    owner_email = await get_owner_email(db, org.id)

    return OrgDetailResponse(
        id=org.id,
        name=org.name,
        owner_email=owner_email,
        user_count=len(users),
        max_users=org.max_users,
        subscription_status=org.subscription_status,
        created_at=org.created_at,
        users=users,
    )


@router.put("/organizations/{org_id}", response_model=OrganizationListResponse)
async def update_org(
    org_id: str, request: UpdateOrgRequest, db: AsyncSession = Depends(get_db_session)
):
    """Update organization settings."""
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    updated = await update_organization(
        db,
        org_id,
        max_users=request.max_users if request.max_users is not None else org.max_users,
    )

    members_result = await db.execute(
        select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == org_id
        )
    )
    user_count = members_result.scalar() or 0
    sub_result = await db.execute(
        select(Subscription).where(Subscription.organization_id == org_id)
    )
    subscription = sub_result.scalar_one_or_none()
    owner_email = await get_owner_email(db, updated.id)

    return OrganizationListResponse(
        id=updated.id,
        name=updated.name,
        owner_email=owner_email,
        user_count=user_count,
        max_users=updated.max_users,
        subscription_status=updated.subscription_status,
        seats=subscription.seats if subscription else 0,
        created_at=updated.created_at,
    )


@router.patch("/organizations/{org_id}/subscription", response_model=OrganizationListResponse)
async def set_subscription_status(
    org_id: str,
    request: UpdateSubscriptionRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Update organization subscription status."""
    valid_statuses = {
        "active",
        "trialing",
        "pending",
        "past_due",
        "canceled",
        "failed",
        "none",
    }
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    updated = await update_subscription_status(db, org_id, request.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Organization not found")

    members_result = await db.execute(
        select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == org_id
        )
    )
    user_count = members_result.scalar() or 0
    sub_result = await db.execute(
        select(Subscription).where(Subscription.organization_id == org_id)
    )
    subscription = sub_result.scalar_one_or_none()
    owner_email = await get_owner_email(db, updated.id)

    return OrganizationListResponse(
        id=updated.id,
        name=updated.name,
        owner_email=owner_email,
        user_count=user_count,
        max_users=updated.max_users,
        subscription_status=updated.subscription_status,
        seats=subscription.seats if subscription else 0,
        created_at=updated.created_at,
    )


@router.delete("/organizations/{org_id}", status_code=204)
async def delete_org(org_id: str, db: AsyncSession = Depends(get_db_session)):
    """Delete organization and all memberships."""
    deleted = await delete_organization(db, org_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Organization not found")


# ─── Users ────────────────────────────────────────────────────────────────────


@router.get("/token-usage", response_model=List[UserTokenStatsResponse])
async def list_token_usage(db: AsyncSession = Depends(get_db_session)):
    """List today's token usage for all users."""
    today = date.today()
    stmt = select(UserTokenUsage).where(UserTokenUsage.date == today)
    result = await db.execute(stmt)
    usages = result.scalars().all()

    out: List[UserTokenStatsResponse] = []
    for usage in usages:
        user = await get_user_by_id(usage.user_id)
        daily_limit = user.daily_token_limit if user else 0
        tokens_used = usage.total_tokens if usage else 0
        remaining = max(0, daily_limit - tokens_used)
        usage_percentage = (tokens_used / daily_limit * 100) if daily_limit > 0 else 0.0
        out.append(
            UserTokenStatsResponse(
                user_id=usage.user_id,
                tokens_used_today=tokens_used,
                daily_limit=daily_limit,
                usage_percentage=usage_percentage,
                remaining_tokens=remaining,
            )
        )
    return out


@router.post("/users", response_model=CreateUserResponse, status_code=201)
async def create_user(request: CreateUserRequest, db: AsyncSession = Depends(get_db_session)):
    """Create a Supabase user and assign to an org (new or existing)."""
    if request.org_mode == "new" and not request.org_name:
        raise HTTPException(status_code=400, detail="org_name required when org_mode='new'")
    if request.org_mode == "existing" and not request.org_id:
        raise HTTPException(status_code=400, detail="org_id required when org_mode='existing'")

    # Create Supabase user
    try:
        created_user = await create_user_admin(
            request.email, request.password, request.first_name, request.last_name
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create user: {e}")

    user_id = created_user.id

    # Set token limit
    try:
        await update_user_token_limit(user_id, request.daily_token_limit)
    except Exception as e:
        logger.warning(f"Failed to set token limit for {user_id}: {e}")

    # Resolve org
    if request.org_mode == "new":
        org = await create_organization(db, request.org_name, 5)
        org = await update_subscription_status(db, org.id, "active")
        role = "owner"
    else:
        org = await db.get(Organization, request.org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        role = "member"

    # Create membership
    try:
        await add_user_to_organization(db, org.id, user_id, role)
    except Exception as e:
        logger.error(f"Failed to create membership for {user_id}: {e}")
        try:
            await delete_user_admin(user_id)
        except Exception as cleanup_err:
            logger.error(f"Failed to cleanup orphan user {user_id}: {cleanup_err}")
        raise HTTPException(status_code=500, detail="Failed to assign user to organization")

    return CreateUserResponse(
        user_id=user_id,
        email=request.email,
        organization_id=org.id,
        organization_name=org.name,
    )


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_details(user_id: str, db: AsyncSession = Depends(get_db_session)):
    """Get user details."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    membership = await get_membership_for_user(db, user_id)
    organization_id = None
    organization_name = None
    role = "user"

    if membership:
        org = await db.get(Organization, membership.organization_id)
        if org:
            organization_id = org.id
            organization_name = org.name
            role = membership.role

    return UserDetailResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        organization_id=organization_id,
        organization_name=organization_name,
        role=role,
        daily_token_limit=user.daily_token_limit,
    )


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: str, request: UpdateUserRequest, db: AsyncSession = Depends(get_db_session)
):
    """Update user settings."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.daily_token_limit is not None:
        await update_user_token_limit(user_id, request.daily_token_limit)

    user = await get_user_by_id(user_id)
    membership = await get_membership_for_user(db, user_id)
    organization_id = None
    organization_name = None
    role = "user"

    if membership:
        org = await db.get(Organization, membership.organization_id)
        if org:
            organization_id = org.id
            organization_name = org.name
            role = membership.role

    return UserDetailResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        organization_id=organization_id,
        organization_name=organization_name,
        role=role,
        daily_token_limit=user.daily_token_limit,
    )


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db_session)):
    """Delete user from Supabase and remove org membership."""
    membership = await get_membership_for_user(db, user_id)
    if membership:
        await remove_user_from_organization(db, membership.organization_id, user_id)

    try:
        await delete_user_admin(user_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete user: {e}")


@router.get(
    "/organizations/{organization_id}/members",
    response_model=List[OrganizationMemberResponse],
)
async def list_organization_members(
    organization_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all members in an organization."""
    org = await db.get(Organization, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id
        )
    )
    memberships = result.scalars().all()

    response = []
    for membership in memberships:
        user = await get_user_by_id(membership.user_id)
        if user:
            response.append(
                OrganizationMemberResponse(
                    id=membership.user_id,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    role=membership.role,
                    joined_at=membership.created_at,
                )
            )
    return response
