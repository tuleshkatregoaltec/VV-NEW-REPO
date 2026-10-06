import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.service import (
    get_user_by_id,
    send_magic_link_email,
    update_user_token_limit,
)
from app.billing.models import CustomerPortalResponse, SubscriptionResponse
from app.billing.service import get_customer_portal_url
from app.config import settings
from app.core.dependencies import (
    AuthContext,
    require_active_owner,
    require_admin,
    require_auth,
    require_owner_membership,
)
from app.organization.models import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    InviteConflictResponse,
    InviteUserRequest,
    InviteUserResponse,
    OperationSuccessResponse,
    OrganizationCreateRequest,
    OrganizationDetailResponse,
    OrganizationInvitation,
    OrganizationInvitationResponse,
    OrganizationMembership,
    OrganizationResponse,
    OrganizationUpdateRequest,
    OrganizationUserDetailResponse,
    OwnerOrganizationCreateRequest,
    OwnerOrganizationCreateResponse,
    UserTokenLimitUpdateResponse,
    UserUpdateRequest,
    ValidateInviteTokenResponse,
)
from app.organization.service import (
    add_user_to_organization,
    cancel_invitation,
    create_invitation,
    expire_pending_invitations,
    get_active_user_count,
    get_invitation_by_id,
    get_invitation_by_token,
    get_member_count,
    get_membership_for_user,
    get_organization_by_id,
    get_pending_invitation_count,
    mark_invitation_accepted,
    remove_user_from_organization,
)
from app.organization.service import (
    create_organization as create_organization_service,
)
from app.organization.service import (
    delete_organization as delete_organization_service,
)
from app.organization.service import (
    list_organizations as list_organizations_service,
)
from app.organization.service import (
    update_organization as update_organization_service,
)
from app.postgres import get_db_session
from app.postgres.models import Organization
from app.providers.auth import AuthenticatedUser
from app.token_usage.service import token_usage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/organization", tags=["organization"])


def _require_owner_org_access(context: AuthContext, org_id: str) -> None:
    if context.organization.id != org_id:
        raise HTTPException(status_code=403, detail="Organization access denied")


async def get_pending_invitation_or_error(db: AsyncSession, token: str):
    invitation = await get_invitation_by_token(db, token)

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.status != "pending":
        if invitation.status == "accepted":
            raise HTTPException(status_code=400, detail="Invitation already accepted")
        raise HTTPException(status_code=400, detail="Invitation is no longer valid")

    now = datetime.now(timezone.utc)
    if invitation.expires_at < now:
        raise HTTPException(status_code=400, detail="Invitation has expired")

    return invitation


@router.post("/create", response_model=OwnerOrganizationCreateResponse)
async def create_owner_organization(
    request: OwnerOrganizationCreateRequest,
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create organization for owner during self-signup (before checkout).

    Idempotent: If user already owns an organization, updates and returns existing org_id.
    This allows users to retry checkout after abandoning payment.
    """
    from uuid import uuid4

    existing_membership = await get_membership_for_user(db, current_user.id)

    if existing_membership:
        if existing_membership.role != "owner":
            raise HTTPException(
                status_code=400,
                detail="You already belong to an organization",
            )

        # User already owns an org - update existing org (retry scenario)
        org = await db.get(Organization, existing_membership.organization_id)
        if not org:
            raise HTTPException(
                status_code=500,
                detail="Organization membership exists but org not found",
            )

        # Update org details for retry
        org.name = request.name
        org.max_users = request.max_users
        org.updated_at = datetime.now(timezone.utc)

        db.add(org)
        await db.commit()
        await db.refresh(org)

        logger.info(
            f"Updated existing org {org.id} for user {current_user.id} (retry/abandon scenario)"
        )

        return OwnerOrganizationCreateResponse(
            organization_id=org.id,
            name=org.name,
            max_users=org.max_users,
            is_new=False,
        )

    # Create new organization
    org_id = str(uuid4())
    org = Organization(
        id=org_id,
        name=request.name,
        max_users=request.max_users,
        subscription_status=None,  # No subscription yet
        stripe_customer_id=None,  # Created during checkout
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(org)

    # Add owner membership
    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=current_user.id,
        role="owner",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(membership)

    try:
        await db.commit()
        await db.refresh(org)
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create organization for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create organization: {str(e)}")

    logger.info(f"Created new organization {org.id} for user {current_user.id}")

    return OwnerOrganizationCreateResponse(
        organization_id=org.id,
        name=org.name,
        max_users=org.max_users,
        is_new=True,
    )


class OrganizationMemberResponse(BaseModel):
    """Organization member response."""

    id: str
    email: str
    first_name: str
    last_name: str
    role: str


@router.get("/members", response_model=List[OrganizationMemberResponse])
async def get_organization_members(
    context: AuthContext = Depends(require_owner_membership),
    db: AsyncSession = Depends(get_db_session),
):
    """Get organization members (query from memberships table)"""
    result = await db.exec(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == context.organization.id
        )
    )
    members = result.all()

    response = []
    for member in members:
        user = await get_user_by_id(member.user_id)
        if user:
            response.append(
                OrganizationMemberResponse(
                    id=member.user_id,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    role=member.role,
                )
            )

    return response


@router.get("/invitations", response_model=List[OrganizationInvitationResponse])
async def get_organization_invitations(
    context: AuthContext = Depends(require_owner_membership),
    db: AsyncSession = Depends(get_db_session),
):
    """Get pending invitations for the current organization."""
    result = await db.exec(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == context.organization.id,
            OrganizationInvitation.status == "pending",
        )
    )
    invitations = result.all()

    now = datetime.now(timezone.utc)
    response = []
    for invitation in invitations:
        if invitation.expires_at < now:
            continue
        response.append(
            OrganizationInvitationResponse(
                id=invitation.id,
                email=invitation.email,
                role=invitation.role,
                status=invitation.status,
                expires_at=invitation.expires_at,
                created_at=invitation.created_at,
            )
        )

    return response


@router.delete("/invitations/{invitation_id}", response_model=OperationSuccessResponse)
async def delete_organization_invitation(
    invitation_id: str,
    context: AuthContext = Depends(require_owner_membership),
    db: AsyncSession = Depends(get_db_session),
):
    """Cancel a pending invitation for the current organization."""
    invitation = await get_invitation_by_id(db, invitation_id)
    if not invitation or invitation.organization_id != context.organization.id:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.status != "pending":
        raise HTTPException(status_code=400, detail="Invitation is no longer pending")

    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has already expired")

    await cancel_invitation(db, invitation)

    return OperationSuccessResponse(success=True)


@router.delete("/members/{user_id}", response_model=OperationSuccessResponse)
async def remove_member(
    user_id: str,
    context: AuthContext = Depends(require_owner_membership),
    db: AsyncSession = Depends(get_db_session),
):
    """Remove user from organization (delete membership to free seat)"""
    if user_id == context.user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from organization")

    success = await remove_user_from_organization(db, context.organization.id, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="User not found in organization")

    return OperationSuccessResponse(success=True)


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_organization_subscription(
    context: AuthContext = Depends(require_owner_membership),
    db: AsyncSession = Depends(get_db_session),
):
    """Get organization subscription details (owner only)."""

    if not context.subscription:
        raise HTTPException(status_code=404, detail="No subscription found")

    current_members = await get_member_count(db, context.organization.id)
    pending_invitations = await get_pending_invitation_count(db, context.organization.id)
    reserved_seats = current_members + pending_invitations
    available_seats = max(0, context.subscription.seats - reserved_seats)
    excess_users = max(0, current_members - context.subscription.seats)

    now = datetime.now(timezone.utc)
    within_paid_period = now < context.subscription.current_period_end

    return SubscriptionResponse(
        id=context.subscription.id,
        organization_id=context.subscription.organization_id,
        status=context.subscription.status,
        seats=context.subscription.seats,
        current_period_end=context.subscription.current_period_end,
        cancel_at_period_end=context.subscription.cancel_at_period_end,
        current_members=current_members,
        available_seats=available_seats,
        excess_users=excess_users,
        within_paid_period=within_paid_period,
    )


@router.get("/customer-portal", response_model=CustomerPortalResponse)
async def get_stripe_customer_portal(
    context: AuthContext = Depends(require_owner_membership),
    db: AsyncSession = Depends(get_db_session),
):
    """Get Stripe Customer Portal URL (admin only)."""

    organization = context.organization

    if not organization.stripe_customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer found")

    return_url = f"{settings.FRONTEND_URL}/settings/organization"
    portal_url = await get_customer_portal_url(organization.stripe_customer_id, return_url)

    return CustomerPortalResponse(url=portal_url)


@router.post("/invite-user", response_model=InviteUserResponse)
async def invite_user_to_organization(
    request: InviteUserRequest,
    context: AuthContext = Depends(require_active_owner),
    db: AsyncSession = Depends(get_db_session),
):
    """Invite user to organization (admin only)."""

    organization = context.organization

    active_user_count = await get_member_count(db, organization.id)
    pending_invitation_count = await get_pending_invitation_count(db, organization.id)
    reserved_seat_count = active_user_count + pending_invitation_count
    if reserved_seat_count >= organization.max_users:
        raise HTTPException(
            status_code=400,
            detail=(
                "Organization has reached maximum seat limit "
                f"({organization.max_users}) including pending invitations"
            ),
        )

    # Create invitation record
    invitation = await create_invitation(
        db=db,
        organization_id=organization.id,
        email=request.email,
        invited_by_user_id=context.user.id,
        role="member",
    )

    redirect_url = f"{settings.FRONTEND_URL}/invite?token={invitation.token}"
    auth_result = await send_magic_link_email(
        email=request.email,
        redirect_url=redirect_url,
    )
    if not auth_result["success"]:
        invitation.status = "expired"
        db.add(invitation)
        await db.commit()
        raise HTTPException(status_code=400, detail=auth_result["error"])

    await expire_pending_invitations(
        db, organization.id, request.email, exclude_token=invitation.token
    )

    return InviteUserResponse(success=True, invitation_token=invitation.token)


@router.get("/validate-invite-token", response_model=ValidateInviteTokenResponse)
async def validate_invite_token(
    token: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Validate invitation token and return organization details."""
    invitation = await get_pending_invitation_or_error(db, token)

    # Get organization details
    organization = await get_organization_by_id(db, invitation.organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    return ValidateInviteTokenResponse(
        organization_name=organization.name,
        organization_id=organization.id,
        role=invitation.role,
        email=invitation.email,
        expires_at=invitation.expires_at,
        status=invitation.status,
    )


@router.post(
    "/accept-invite",
    response_model=AcceptInviteResponse,
)
async def accept_invite(
    request: AcceptInviteRequest,
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    """Accept organization invitation with conflict detection."""
    invitation = await get_pending_invitation_or_error(db, request.token)

    # Validate email matches
    if invitation.email.lower() != current_user.email.lower():
        raise HTTPException(status_code=403, detail="Invitation email does not match your account")

    # Check for existing membership (conflict detection)
    existing_membership = await get_membership_for_user(db, current_user.id)

    if existing_membership:
        # User already has a membership - return conflict details
        current_org = await get_organization_by_id(db, existing_membership.organization_id)
        if not current_org:
            raise HTTPException(status_code=500, detail="Current organization not found")

        member_count = await get_member_count(db, current_org.id)
        is_single_seat = member_count == 1

        conflict_response = InviteConflictResponse(
            conflict=True,
            current_org_id=current_org.id,
            current_org_name=current_org.name,
            current_role=existing_membership.role,
            member_count=member_count,
            is_single_seat=is_single_seat,
        )
        raise HTTPException(status_code=409, detail=conflict_response.model_dump())

    organization = await get_organization_by_id(db, invitation.organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    member_count = await get_member_count(db, organization.id)
    if member_count >= organization.max_users:
        raise HTTPException(
            status_code=409,
            detail="This organization has no available seats left for this invitation.",
        )

    # No conflict - create membership
    await add_user_to_organization(
        db=db,
        org_id=invitation.organization_id,
        user_id=current_user.id,
        role=invitation.role,
    )

    # Mark invitation as accepted
    await mark_invitation_accepted(db, invitation)

    return AcceptInviteResponse(
        success=True,
        organization_id=organization.id,
        organization_name=organization.name,
        role=invitation.role,
    )


# --- Organization management endpoints (migrated from admin) ---


@router.post(
    "/organizations",
    status_code=201,
    response_model=OrganizationResponse,
)
async def create_organization(
    organization_in: OrganizationCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _admin_user: AuthenticatedUser = Depends(require_admin),
):
    """Create a new organization (admin only)."""
    if not await get_user_by_id(organization_in.owner_id):
        raise HTTPException(status_code=404, detail="Owner user not found")

    existing_membership = await get_membership_for_user(db, organization_in.owner_id)
    if existing_membership:
        raise HTTPException(
            status_code=400,
            detail="Owner user already belongs to an organization",
        )

    organization = None
    try:
        organization = await create_organization_service(
            db=db,
            name=organization_in.name,
            max_users=organization_in.max_users,
        )
        await add_user_to_organization(
            db=db,
            org_id=organization.id,
            user_id=organization_in.owner_id,
            role="owner",
        )
        response = OrganizationResponse.model_validate(organization)
        response.active_user_count = 1
        return response
    except Exception as e:
        if organization is not None:
            try:
                await delete_organization_service(db, organization.id)
            except Exception:
                logger.exception(
                    "Failed to clean up organization %s after owner membership error",
                    organization.id,
                )
        logger.exception(f"Failed to create organization: {e}")
        raise HTTPException(status_code=400, detail="Failed to create organization")


@router.get("/organizations", response_model=List[OrganizationResponse])
async def list_organization(
    db: AsyncSession = Depends(get_db_session), _admin: None = Depends(require_admin)
):
    """List all organizations with user counts (admin only)."""
    organizations = await list_organizations_service(db)

    result = []
    for org in organizations:
        active_count = await get_active_user_count(db, org.id)
        response = OrganizationResponse.model_validate(org)
        response.active_user_count = active_count
        result.append(response)

    return result


@router.get("/organizations/{org_id}", response_model=OrganizationDetailResponse)
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db_session),
    context: AuthContext = Depends(require_owner_membership),
):
    """Get organization details with user list (organization admin)."""
    _require_owner_org_access(context, org_id)

    organization = await get_organization_by_id(db, org_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    active_count = await get_active_user_count(db, org_id)

    user_list = []

    # Get all memberships for this organization
    memberships_result = await db.exec(
        select(OrganizationMembership).where(OrganizationMembership.organization_id == org_id)
    )
    memberships = memberships_result.all()

    for membership in memberships:
        user = await get_user_by_id(membership.user_id)

        if user is not None:
            usage = await token_usage_service.get_today_usage(db, user.id)
            tokens_used = usage.total_tokens if usage else 0
            daily_limit = user.daily_token_limit
            usage_percentage = (tokens_used / daily_limit * 100) if daily_limit > 0 else 0

            user_list.append(
                OrganizationUserDetailResponse(
                    id=user.id,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    created_at=user.created_at,
                    last_login=user.last_login_at,
                    daily_token_limit=daily_limit,
                    tokens_used_today=tokens_used,
                    usage_percentage=usage_percentage,
                )
            )

    org_response = OrganizationResponse.model_validate(organization)
    org_response.active_user_count = active_count

    return OrganizationDetailResponse(
        organization=org_response,
        users=user_list,
    )


@router.put("/organizations/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    organization_update: OrganizationUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    context: AuthContext = Depends(require_owner_membership),
):
    """Update organization settings (organization admin)."""
    _require_owner_org_access(context, org_id)

    organization = await update_organization_service(
        db=db,
        org_id=org_id,
        max_users=organization_update.max_users,
    )

    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    active_count = await get_active_user_count(db, org_id)

    response = OrganizationResponse.model_validate(organization)
    response.active_user_count = active_count
    return response


@router.delete("/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db_session),
    _admin: None = Depends(require_admin),
):
    """Delete organization (admin only)."""
    success = await delete_organization_service(db, org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Organization not found")
    return None


@router.put("/users/{user_id}", response_model=UserTokenLimitUpdateResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    context: AuthContext = Depends(require_owner_membership),
) -> UserTokenLimitUpdateResponse:
    """Update user daily token limit (organization admin)."""

    if user_update.daily_token_limit is None:
        raise HTTPException(status_code=400, detail="daily_token_limit is required")

    membership = await get_membership_for_user(db, user_id)
    if not membership or membership.organization_id != context.organization.id:
        raise HTTPException(status_code=404, detail="User not found in organization")

    await update_user_token_limit(user_id, user_update.daily_token_limit)

    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserTokenLimitUpdateResponse(
        id=user.id,
        email=user.email,
        daily_token_limit=user.daily_token_limit,
        updated_at=user.updated_at,
    )
