from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.billing.models import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PaymentSyncResponse,
)
from app.billing.service import create_checkout_session, sync_after_checkout
from app.core.dependencies import require_auth
from app.postgres import get_db_session
from app.providers.auth import AuthenticatedUser

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.post("/create-checkout", response_model=CheckoutSessionResponse)
async def create_checkout_session_endpoint(
    request: CheckoutSessionRequest,
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create Stripe checkout session for existing organization.

    Organization must already exist (created via /organization/create).
    User profile (first_name/last_name) must be set in auth metadata.
    """
    # Verify user has profile set
    if not current_user.first_name or not current_user.last_name:
        raise HTTPException(
            status_code=400,
            detail="Profile incomplete. Please set first name and last name before checkout.",
        )

    try:
        result = await create_checkout_session(
            user_id=current_user.id,
            email=current_user.email,
            organization_id=request.organization_id,
            seats=request.seats,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            price_tier=request.price_tier,
            db=db,
        )
        return CheckoutSessionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SyncAfterCheckoutRequest(BaseModel):
    """Request to sync after checkout"""

    session_id: str


@router.post("/sync-after-checkout", response_model=PaymentSyncResponse)
async def sync_after_checkout_endpoint(
    request: SyncAfterCheckoutRequest,
    current_user: AuthenticatedUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    """Eager sync after checkout success."""
    result = await sync_after_checkout(
        session_id=request.session_id,
        user_id=current_user.id,
        db=db,
    )
    return result
