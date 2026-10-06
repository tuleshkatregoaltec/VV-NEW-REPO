from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.billing.models import Subscription
from app.core.dependencies import (
    require_active_subscription,
    require_admin,
    require_auth,
    require_owner_membership,
)
from app.organization.models import Organization, OrganizationMembership


class FakeExecResult:
    def __init__(self, first_value):
        self._first_value = first_value

    def first(self):
        return self._first_value


class FakeDB:
    def __init__(self, organization=None, subscription=None):
        self.organization = organization
        self.subscription = subscription

    async def get(self, model, key):
        return self.organization

    async def exec(self, query):
        return FakeExecResult(self.subscription)


def make_user(**overrides):
    user = SimpleNamespace(
        id="user-1",
        email="owner@example.com",
        is_authenticated=True,
        first_name="Owner",
        last_name="User",
        daily_token_limit=500000,
        app_metadata=SimpleNamespace(is_admin=False, daily_token_limit=500000),
        user_metadata=SimpleNamespace(first_name="Owner", last_name="User"),
        is_admin=False,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def make_membership(role="owner", organization_id="org-1"):
    return OrganizationMembership(
        organization_id=organization_id,
        user_id="user-1",
        role=role,
    )


def make_org(subscription_status="active", organization_id="org-1"):
    return Organization(
        id=organization_id,
        name="Acme",
        max_users=5,
        subscription_status=subscription_status,
        stripe_customer_id="cus_123",
    )


def make_subscription(organization_id="org-1"):
    return Subscription(
        id="sub-local-1",
        organization_id=organization_id,
        stripe_subscription_id="sub_123",
        stripe_customer_id="cus_123",
        stripe_price_id="price_123",
        status="active",
        seats=5,
        current_period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        current_period_end=datetime(2026, 2, 1, tzinfo=timezone.utc),
        cancel_at_period_end=False,
    )


@pytest.mark.asyncio
async def test_require_auth_rejects_unauthenticated_request():
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))

    with pytest.raises(HTTPException) as exc:
        await require_auth(request)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin_user():
    with pytest.raises(HTTPException) as exc:
        await require_admin(SimpleNamespace(user=make_user(email="owner@example.com")))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_active_subscription_rejects_user_without_membership(monkeypatch):
    from app.core import dependencies

    async def fake_membership(db, user_id):
        return None

    monkeypatch.setattr(dependencies, "get_membership_for_user", fake_membership)

    with pytest.raises(HTTPException) as exc:
        await require_active_subscription(make_user(), FakeDB())

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "NO_ORG_MEMBERSHIP"


@pytest.mark.asyncio
async def test_require_active_subscription_rejects_missing_organization(monkeypatch):
    from app.core import dependencies

    async def fake_membership(db, user_id):
        return make_membership()

    monkeypatch.setattr(dependencies, "get_membership_for_user", fake_membership)

    with pytest.raises(HTTPException) as exc:
        await require_active_subscription(make_user(), FakeDB(organization=None))

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_require_active_subscription_rejects_past_due_organization(monkeypatch):
    from app.core import dependencies

    async def fake_membership(db, user_id):
        return make_membership()

    monkeypatch.setattr(dependencies, "get_membership_for_user", fake_membership)

    with pytest.raises(HTTPException) as exc:
        await require_active_subscription(make_user(), FakeDB(organization=make_org("past_due")))

    assert exc.value.status_code == 402
    assert exc.value.detail["code"] == "SUBSCRIPTION_PAST_DUE"


@pytest.mark.asyncio
async def test_require_active_subscription_rejects_inactive_organization(monkeypatch):
    from app.core import dependencies

    async def fake_membership(db, user_id):
        return make_membership()

    monkeypatch.setattr(dependencies, "get_membership_for_user", fake_membership)

    with pytest.raises(HTTPException) as exc:
        await require_active_subscription(make_user(), FakeDB(organization=make_org("canceled")))

    assert exc.value.status_code == 402
    assert exc.value.detail["code"] == "SUBSCRIPTION_REQUIRED"


@pytest.mark.asyncio
async def test_require_active_subscription_allows_trialing_organization(monkeypatch):
    from app.core import dependencies

    async def fake_membership(db, user_id):
        return make_membership(role="member")

    monkeypatch.setattr(dependencies, "get_membership_for_user", fake_membership)

    context = await require_active_subscription(
        make_user(),
        FakeDB(organization=make_org("trialing"), subscription=make_subscription()),
    )

    assert context.organization.subscription_status == "trialing"
    assert context.membership.role == "member"
    assert context.subscription.stripe_subscription_id == "sub_123"


@pytest.mark.asyncio
async def test_require_owner_membership_rejects_member_role(monkeypatch):
    from app.core import dependencies

    async def fake_membership(db, user_id):
        return make_membership(role="member")

    monkeypatch.setattr(dependencies, "get_membership_for_user", fake_membership)

    with pytest.raises(HTTPException) as exc:
        await require_owner_membership(make_user(), FakeDB(organization=make_org("active")))

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "OWNER_REQUIRED"
