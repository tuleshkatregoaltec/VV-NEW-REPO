import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from uuid import uuid4

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.organization.models import OrganizationInvitation, OrganizationMembership
from app.postgres.models import Organization


async def get_free_org_id(db: AsyncSession):
    done = False
    while not done:
        uuid = uuid4()
        uuid_str = str(uuid)

        done = await get_organization_by_id(db, uuid_str) is None
    return uuid_str


async def get_organization_by_id(db: AsyncSession, org_id: str) -> Organization | None:
    """Get organization by ID"""
    return await db.get(Organization, org_id)


async def get_membership_for_user(
    db: AsyncSession, user_id: str
) -> Optional[OrganizationMembership]:
    """
    Get membership for user.

    Invariant: Returns exactly zero or one membership (enforced by UNIQUE user_id).
    Raises RuntimeError if constraint violated.
    """
    result = await db.exec(
        select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
    )
    memberships = result.all()

    if len(memberships) > 1:
        raise RuntimeError(
            f"Constraint violation: User {user_id} has {len(memberships)} memberships. "
            "Expected at most one due to UNIQUE(user_id) constraint."
        )

    return memberships[0] if memberships else None


async def get_owner_membership_for_org(
    db: AsyncSession, org_id: str
) -> Optional[OrganizationMembership]:
    result = await db.exec(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.role == "owner",
        )
    )
    return result.first()


async def get_organization_for_user(db: AsyncSession, user_id: str) -> Organization | None:
    """Get organization via membership (replaces JSONB lookup)"""
    membership = await get_membership_for_user(db, user_id)
    if not membership:
        return None
    return await db.get(Organization, membership.organization_id)


async def get_member_count(db: AsyncSession, org_id: str) -> int:
    """Count members (replaces JSONB counting)"""
    result = await db.exec(
        select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == org_id
        )
    )
    return result.first()


async def get_active_user_count(db: AsyncSession, org_id: str) -> int:
    """Count active users in an organization (alias for get_member_count)"""
    return await get_member_count(db, org_id)


async def get_pending_invitation_count(db: AsyncSession, org_id: str) -> int:
    """Count non-expired pending invitations for seat reservation checks."""
    now = datetime.now(timezone.utc)
    result = await db.exec(
        select(func.count(OrganizationInvitation.id)).where(
            OrganizationInvitation.organization_id == org_id,
            OrganizationInvitation.status == "pending",
            OrganizationInvitation.expires_at >= now,
        )
    )
    return result.first()


async def create_organization(db: AsyncSession, name: str, max_users: int) -> Organization:
    organization = Organization(
        id=await get_free_org_id(db),
        name=name,
        max_users=max_users,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return organization


async def list_organizations(db: AsyncSession) -> Sequence[Organization]:
    """List all organizations"""
    organizations = await db.exec(select(Organization))
    return organizations.all()


async def update_organization(db: AsyncSession, org_id: str, max_users: int) -> Organization | None:
    """Update organization settings"""
    organization = await db.get(Organization, org_id)

    if not organization:
        return None

    organization.max_users = max_users
    organization.updated_at = datetime.now(timezone.utc)

    db.add(organization)
    await db.commit()
    await db.refresh(organization)

    return organization


async def add_user_to_organization(
    db: AsyncSession, org_id: str, user_id: str, role: str = "member"
) -> OrganizationMembership:
    """Create membership record"""
    membership = OrganizationMembership(
        organization_id=org_id,
        user_id=user_id,
        role=role,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


async def remove_user_from_organization(db: AsyncSession, org_id: str, user_id: str) -> bool:
    """Delete membership to free seat"""
    result = await db.exec(
        select(OrganizationMembership)
        .where(OrganizationMembership.organization_id == org_id)
        .where(OrganizationMembership.user_id == user_id)
    )
    membership = result.first()
    if not membership:
        return False

    await db.delete(membership)
    await db.commit()
    return True


async def update_subscription_status(
    db: AsyncSession, org_id: str, status: str
) -> Organization | None:
    """Update organization subscription status."""
    org = await db.get(Organization, org_id)
    if not org:
        return None
    org.subscription_status = status
    org.updated_at = datetime.now(timezone.utc)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


async def delete_organization(db: AsyncSession, org_id: str) -> bool:
    """Delete organization from WorkOS and local DB"""
    organization = await db.get(Organization, org_id)

    if not organization:
        return False

    # Delete locally
    await db.delete(organization)
    await db.commit()

    return True


def generate_invitation_token() -> str:
    """Generate secure random token for invitation"""
    return secrets.token_urlsafe(32)


async def create_invitation(
    db: AsyncSession,
    organization_id: str,
    email: str,
    invited_by_user_id: str,
    role: str = "member",
    expires_in_days: int = 7,
) -> OrganizationInvitation:
    """Create organization invitation record"""
    token = generate_invitation_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=email,
        role=role,
        token=token,
        status="pending",
        invited_by_user_id=invited_by_user_id,
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )

    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def expire_pending_invitations(
    db: AsyncSession, organization_id: str, email: str, exclude_token: str | None = None
) -> int:
    """Invalidate older pending invitations for the same org/email."""
    result = await db.exec(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.status == "pending",
        )
    )
    invitations = result.all()
    if not invitations:
        return 0

    now = datetime.now(timezone.utc)
    for invitation in invitations:
        if exclude_token and invitation.token == exclude_token:
            continue
        invitation.status = "expired"
        invitation.expires_at = now
        db.add(invitation)

    await db.commit()
    return len([invitation for invitation in invitations if invitation.token != exclude_token])


async def get_invitation_by_token(db: AsyncSession, token: str) -> Optional[OrganizationInvitation]:
    """Get invitation by token"""
    result = await db.exec(
        select(OrganizationInvitation).where(OrganizationInvitation.token == token)
    )
    return result.first()


async def get_invitation_by_id(
    db: AsyncSession, invitation_id: str
) -> Optional[OrganizationInvitation]:
    """Get invitation by ID."""
    return await db.get(OrganizationInvitation, invitation_id)


async def mark_invitation_accepted(
    db: AsyncSession, invitation: OrganizationInvitation
) -> OrganizationInvitation:
    """Mark invitation as accepted"""
    invitation.status = "accepted"
    invitation.accepted_at = datetime.now(timezone.utc)
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def cancel_invitation(
    db: AsyncSession, invitation: OrganizationInvitation
) -> OrganizationInvitation:
    """Cancel a pending invitation and free its reserved seat."""
    invitation.status = "declined"
    invitation.expires_at = datetime.now(timezone.utc)
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return invitation
