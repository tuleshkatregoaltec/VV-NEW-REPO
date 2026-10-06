from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import AuthMeResponse, UpdateProfileRequest, UpdateProfileResponse
from app.auth.service import update_user_profile_metadata
from app.core.dependencies import require_auth
from app.organization import service as organization_service
from app.postgres import get_db_session
from app.providers.auth import AuthenticatedUser

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def derive_role(current_user: AuthenticatedUser, organization_role: str | None) -> str:
    if current_user.is_admin:
        return "admin"
    return organization_role or "user"


@router.get("/me", response_model=AuthMeResponse)
async def get_user(
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(require_auth),
) -> AuthMeResponse:
    """
    Get current authenticated user with organization and subscription context.

    Returns first_name/last_name from the authenticated user principal.
    Returns subscription_status from organization.subscription_status (single source of truth).
    """

    # Get organization via membership
    membership = await organization_service.get_membership_for_user(db, current_user.id)

    organization_id = None
    organization_name = None
    organization_role = None
    is_owner = False
    subscription_status = None

    if membership:
        from app.postgres.models import Organization

        is_owner = membership.role == "owner"
        organization_role = membership.role

        org = await db.get(Organization, membership.organization_id)
        if org:
            organization_id = org.id
            organization_name = org.name

            # Use org.subscription_status as single source of truth
            subscription_status = org.subscription_status

    role = derive_role(current_user, organization_role)

    return AuthMeResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        avatar_url=getattr(current_user, "avatar_url", None),
        organization_id=organization_id,
        organization_name=organization_name,
        role=role,
        is_owner=is_owner,
        subscription_status=subscription_status,
    )


@router.post("/update-profile", response_model=UpdateProfileResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: AuthenticatedUser = Depends(require_auth),
):
    """Update user profile (first name and last name)."""
    await update_user_profile_metadata(current_user.id, request.first_name, request.last_name)

    return UpdateProfileResponse(
        success=True, first_name=request.first_name, last_name=request.last_name
    )
