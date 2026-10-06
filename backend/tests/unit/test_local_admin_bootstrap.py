from datetime import datetime, timezone

import pytest

from app.billing.models import Subscription
from app.organization.models import Organization, OrganizationMembership
from scripts.admin import bootstrap_local_admin_state as bootstrap


class FakeExecResult:
    def __init__(self, first_value):
        self._first_value = first_value

    def first(self):
        return self._first_value


class FakeDB:
    def __init__(self, organization=None, membership=None, subscription=None):
        self.organization = organization
        self.membership = membership
        self.subscription = subscription
        self.commit_count = 0
        self.refresh_targets = []
        self.added_models = []
        self.exec_results = [membership, subscription]

    async def exec(self, query):
        return FakeExecResult(self.exec_results.pop(0))

    async def get(self, model, key):
        return self.organization

    def add(self, model):
        self.added_models.append(model)
        if isinstance(model, Organization):
            self.organization = model
        elif isinstance(model, OrganizationMembership):
            self.membership = model
        elif isinstance(model, Subscription):
            self.subscription = model

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, model):
        self.refresh_targets.append(model)


def make_org(**overrides):
    organization = Organization(
        id="org-1",
        name="Existing Org",
        max_users=2,
        subscription_status="pending",
        stripe_customer_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    for key, value in overrides.items():
        setattr(organization, key, value)
    return organization


def make_membership(**overrides):
    membership = OrganizationMembership(
        id="membership-1",
        organization_id="org-1",
        user_id="user-1",
        role="member",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    for key, value in overrides.items():
        setattr(membership, key, value)
    return membership


def make_subscription(**overrides):
    subscription = Subscription(
        id="sub-1",
        organization_id="org-1",
        stripe_subscription_id="sub_existing",
        stripe_customer_id="cus_existing",
        stripe_price_id="price_existing",
        status="pending",
        seats=2,
        current_period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        current_period_end=datetime(2026, 2, 1, tzinfo=timezone.utc),
        cancel_at_period_end=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    for key, value in overrides.items():
        setattr(subscription, key, value)
    return subscription


def test_get_bootstrap_admin_user_returns_existing_user(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "FIRST_SUPERUSER", "admin@example.com")
    monkeypatch.setattr(
        bootstrap,
        "_list_auth_users",
        lambda: [{"id": "user-1", "email": "admin@example.com"}],
    )

    user = bootstrap.get_bootstrap_admin_user()

    assert user["id"] == "user-1"


def test_get_bootstrap_admin_user_bootstraps_and_retries(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "FIRST_SUPERUSER", "admin@example.com")
    calls = {"count": 0}

    def fake_list_auth_users():
        calls["count"] += 1
        if calls["count"] < 3:
            return []
        return [{"id": "user-1", "email": "admin@example.com"}]

    create_calls = {"count": 0}

    monkeypatch.setattr(bootstrap, "_list_auth_users", fake_list_auth_users)
    monkeypatch.setattr(bootstrap, "create_user", lambda: create_calls.__setitem__("count", 1))
    monkeypatch.setattr(bootstrap.time, "sleep", lambda _seconds: None)

    user = bootstrap.get_bootstrap_admin_user()

    assert user["id"] == "user-1"
    assert create_calls["count"] == 1


def test_get_bootstrap_admin_user_raises_after_retry(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "FIRST_SUPERUSER", "admin@example.com")
    monkeypatch.setattr(bootstrap, "_list_auth_users", lambda: [])
    monkeypatch.setattr(bootstrap, "create_user", lambda: None)
    monkeypatch.setattr(bootstrap.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(bootstrap, "AUTH_LOOKUP_RETRIES", 2)

    with pytest.raises(RuntimeError, match="was not found in auth after bootstrap retry"):
        bootstrap.get_bootstrap_admin_user()


@pytest.mark.asyncio
async def test_ensure_local_admin_state_creates_org_membership_and_subscription(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "STRIPE_PRICE_ID_TIER1", "price_tier_1")
    db = FakeDB()

    organization, membership, subscription = await bootstrap.ensure_local_admin_state(
        db,
        user_id="user-1",
        user_email="admin@example.com",
    )

    assert db.commit_count == 1
    assert organization.name == bootstrap.LOCAL_ADMIN_ORG_NAME
    assert organization.subscription_status == "active"
    assert organization.max_users == bootstrap.LOCAL_ADMIN_SEAT_COUNT
    assert organization.stripe_customer_id == "cus_local_admin_user-1"
    assert membership.role == "owner"
    assert membership.organization_id == organization.id
    assert subscription.organization_id == organization.id
    assert subscription.status == "active"
    assert subscription.seats == bootstrap.LOCAL_ADMIN_SEAT_COUNT
    assert subscription.stripe_price_id == "price_tier_1"
    assert subscription.cancel_at_period_end is False


@pytest.mark.asyncio
async def test_ensure_local_admin_state_upgrades_existing_membership_and_subscription(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "STRIPE_PRICE_ID_TIER1", "price_tier_1")
    organization = make_org()
    membership = make_membership()
    subscription = make_subscription()
    db = FakeDB(organization=organization, membership=membership, subscription=subscription)

    (
        ensured_org,
        ensured_membership,
        ensured_subscription,
    ) = await bootstrap.ensure_local_admin_state(
        db,
        user_id="user-1",
        user_email="admin@example.com",
    )

    assert db.commit_count == 1
    assert ensured_org.id == organization.id
    assert ensured_org.subscription_status == "active"
    assert ensured_org.max_users == bootstrap.LOCAL_ADMIN_SEAT_COUNT
    assert ensured_org.stripe_customer_id == "cus_local_admin_user-1"
    assert ensured_membership.role == "owner"
    assert ensured_subscription.id == subscription.id
    assert ensured_subscription.status == "active"
    assert ensured_subscription.seats == bootstrap.LOCAL_ADMIN_SEAT_COUNT
    assert ensured_subscription.cancel_at_period_end is False
