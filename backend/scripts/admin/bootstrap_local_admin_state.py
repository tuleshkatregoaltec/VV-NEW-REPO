import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import requests
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.billing.models import Subscription
from app.config import settings
from app.organization.models import OrganizationMembership
from app.postgres import close_postgres, get_postgres_engine
from app.postgres.models import Organization
from scripts.admin.create_auth_admin_user import create_user

LOCAL_ADMIN_ORG_NAME = "Vitevue Admin Workspace"
LOCAL_ADMIN_SEAT_COUNT = 5
LOCAL_ADMIN_FIRST_NAME = "Admin"
LOCAL_ADMIN_LAST_NAME = "User"
AUTH_LOOKUP_RETRIES = 5
AUTH_LOOKUP_DELAY_SECONDS = 1.0


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.AUTH_SERVICE_ROLE_KEY}",
        "apikey": settings.AUTH_SERVICE_ROLE_KEY,
        "Content-Type": "application/json",
    }


def _list_auth_users() -> list[dict]:
    if not settings.bootstrap_superuser_enabled:
        raise RuntimeError("FIRST_SUPERUSER and FIRST_SUPERUSER_PASSWORD must be configured")
    users: list[dict] = []
    page = 1
    per_page = 200

    while True:
        response = requests.get(
            f"{settings.AUTH_URL}/admin/users?page={page}&per_page={per_page}",
            headers=_headers(),
            timeout=10,
        )
        response.raise_for_status()
        page_users = response.json().get("users", [])
        users.extend(page_users)
        if len(page_users) < per_page:
            break
        page += 1

    return users


def get_bootstrap_admin_user() -> dict:
    existing_user = next(
        (user for user in _list_auth_users() if user.get("email") == settings.FIRST_SUPERUSER),
        None,
    )
    if existing_user is not None:
        return existing_user

    create_user()

    for _ in range(AUTH_LOOKUP_RETRIES):
        existing_user = next(
            (user for user in _list_auth_users() if user.get("email") == settings.FIRST_SUPERUSER),
            None,
        )
        if existing_user is not None:
            return existing_user
        time.sleep(AUTH_LOOKUP_DELAY_SECONDS)

    raise RuntimeError(
        f"Bootstrap admin user {settings.FIRST_SUPERUSER} was not found in auth after bootstrap retry"
    )


async def ensure_local_admin_state(
    db: AsyncSession,
    *,
    user_id: str,
    user_email: str,
) -> tuple[Organization, OrganizationMembership, Subscription]:
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=365)

    result = await db.exec(
        select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
    )
    membership = result.first()

    if membership:
        organization = await db.get(Organization, membership.organization_id)
        if organization is None:
            raise RuntimeError(
                f"Organization {membership.organization_id} for bootstrap admin {user_email} was not found"
            )

        if membership.role != "owner":
            membership.role = "owner"
            membership.updated_at = now
            db.add(membership)
    else:
        organization = Organization(
            id=str(uuid4()),
            name=LOCAL_ADMIN_ORG_NAME,
            max_users=LOCAL_ADMIN_SEAT_COUNT,
            subscription_status="active",
            stripe_customer_id=f"cus_local_admin_{user_id}",
            created_at=now,
            updated_at=now,
        )
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user_id,
            role="owner",
            created_at=now,
            updated_at=now,
        )
        db.add(organization)
        db.add(membership)

    organization.subscription_status = "active"
    organization.max_users = max(organization.max_users, LOCAL_ADMIN_SEAT_COUNT)
    organization.updated_at = now
    organization.stripe_customer_id = (
        organization.stripe_customer_id or f"cus_local_admin_{user_id}"
    )
    db.add(organization)

    subscription_result = await db.exec(
        select(Subscription).where(Subscription.organization_id == organization.id)
    )
    subscription = subscription_result.first()

    if subscription is None:
        subscription = Subscription(
            id=str(uuid4()),
            organization_id=organization.id,
            stripe_subscription_id=f"sub_local_admin_{organization.id}",
            stripe_customer_id=organization.stripe_customer_id,
            stripe_price_id=settings.STRIPE_PRICE_ID_TIER1,
            status="active",
            seats=organization.max_users,
            current_period_start=now,
            current_period_end=period_end,
            cancel_at_period_end=False,
            created_at=now,
            updated_at=now,
        )
    else:
        subscription.stripe_customer_id = organization.stripe_customer_id
        subscription.stripe_price_id = (
            subscription.stripe_price_id or settings.STRIPE_PRICE_ID_TIER1
        )
        subscription.status = "active"
        subscription.seats = organization.max_users
        subscription.current_period_start = now
        subscription.current_period_end = period_end
        subscription.cancel_at_period_end = False
        subscription.updated_at = now

    db.add(subscription)
    await db.commit()
    await db.refresh(organization)
    await db.refresh(membership)
    await db.refresh(subscription)

    return organization, membership, subscription


async def bootstrap_local_admin_state() -> None:
    admin_user = get_bootstrap_admin_user()
    user_id = admin_user["id"]
    user_email = admin_user.get("email") or str(settings.FIRST_SUPERUSER)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(
        get_postgres_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as db:
        organization, _, subscription = await ensure_local_admin_state(
            db,
            user_id=user_id,
            user_email=user_email,
        )

    print("Local admin application state ensured.")
    print(f"email: '{user_email}'")
    print(f"organization_id: '{organization.id}'")
    print(f"subscription_status: '{subscription.status}'")

    await close_postgres()


if __name__ == "__main__":
    import asyncio

    asyncio.run(bootstrap_local_admin_state())
