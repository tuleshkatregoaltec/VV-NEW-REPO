from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.billing.service import create_checkout_session, sync_after_checkout
from app.organization.models import Organization, OrganizationMembership


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, organization=None, membership=None, execute_results=None):
        self.organization = organization
        self.membership = membership
        self.execute_results = list(execute_results or [])
        self.commit_count = 0
        self.refresh_count = 0
        self.rollback_count = 0

    async def get(self, model, key):
        return self.organization

    async def execute(self, stmt):
        if self.execute_results:
            return FakeScalarResult(self.execute_results.pop(0))
        return FakeScalarResult(self.membership)

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, model):
        self.refresh_count += 1

    async def rollback(self):
        self.rollback_count += 1


def make_org(**overrides):
    organization = Organization(
        id="org-1",
        name="Acme",
        max_users=5,
        subscription_status="none",
        stripe_customer_id=None,
    )
    for key, value in overrides.items():
        setattr(organization, key, value)
    return organization


def make_membership(role="owner"):
    return OrganizationMembership(
        organization_id="org-1",
        user_id="user-1",
        role=role,
    )


@pytest.mark.asyncio
async def test_create_checkout_session_requires_existing_organization():
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(
            user_id="user-1",
            email="owner@example.com",
            organization_id="missing-org",
            seats=5,
            first_name="Ada",
            last_name="Lovelace",
            price_tier="tier1",
            db=FakeDB(),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_checkout_session_requires_owner_membership():
    org = make_org()

    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(
            user_id="user-1",
            email="owner@example.com",
            organization_id=org.id,
            seats=5,
            first_name="Ada",
            last_name="Lovelace",
            price_tier="tier1",
            db=FakeDB(organization=org, execute_results=[None]),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_checkout_session_marks_org_failed_when_price_config_is_invalid(monkeypatch):
    from app.billing import service

    org = make_org(stripe_customer_id="cus_existing")
    db = FakeDB(organization=org, execute_results=[make_membership()])

    monkeypatch.setattr(service.settings, "STRIPE_PRICE_ID_TIER1", "bad-price")
    monkeypatch.setattr(service.settings, "STRIPE_PRICE_ID_TIER2", "price_tier_2")

    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(
            user_id="user-1",
            email="owner@example.com",
            organization_id=org.id,
            seats=7,
            first_name="Ada",
            last_name="Lovelace",
            price_tier="tier1",
            db=db,
        )

    assert exc.value.status_code == 500
    assert org.subscription_status == "failed"
    assert org.max_users == 7


@pytest.mark.asyncio
async def test_create_checkout_session_returns_checkout_session(monkeypatch):
    from app.billing import service

    org = make_org()
    db = FakeDB(organization=org, execute_results=[make_membership()])

    monkeypatch.setattr(service.settings, "STRIPE_PRICE_ID_TIER1", "price_tier_1")
    monkeypatch.setattr(service.settings, "STRIPE_PRICE_ID_TIER2", "price_tier_2")
    monkeypatch.setattr(
        service.stripe.Customer,
        "create",
        lambda **kwargs: SimpleNamespace(id="cus_123"),
    )
    monkeypatch.setattr(
        service.stripe.checkout.Session,
        "create",
        lambda **kwargs: SimpleNamespace(
            id="cs_test_123", url="https://checkout.stripe.test/session"
        ),
    )

    result = await create_checkout_session(
        user_id="user-1",
        email="owner@example.com",
        organization_id=org.id,
        seats=8,
        first_name="Ada",
        last_name="Lovelace",
        price_tier="tier1",
        db=db,
    )

    assert result["session_id"] == "cs_test_123"
    assert result["organization_id"] == org.id
    assert org.subscription_status == "pending"
    assert org.stripe_customer_id == "cus_123"
    assert org.max_users == 8


@pytest.mark.asyncio
async def test_sync_after_checkout_requires_completed_session(monkeypatch):
    from app.billing import service

    monkeypatch.setattr(
        service.stripe.checkout.Session,
        "retrieve",
        lambda session_id: SimpleNamespace(status="open", customer="cus_123"),
    )

    with pytest.raises(HTTPException) as exc:
        await sync_after_checkout("cs_test_123", "user-1", FakeDB())

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_sync_after_checkout_requires_owner(monkeypatch):
    from app.billing import service

    org = make_org(stripe_customer_id="cus_123")
    db = FakeDB(organization=org, execute_results=[org, None])

    monkeypatch.setattr(
        service.stripe.checkout.Session,
        "retrieve",
        lambda session_id: SimpleNamespace(status="complete", customer="cus_123"),
    )

    with pytest.raises(HTTPException) as exc:
        await sync_after_checkout("cs_test_123", "user-1", db)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_sync_after_checkout_returns_synced_state(monkeypatch):
    from app.billing import service

    org = make_org(stripe_customer_id="cus_123")
    db = FakeDB(organization=org, execute_results=[org, make_membership()])

    monkeypatch.setattr(
        service.stripe.checkout.Session,
        "retrieve",
        lambda session_id: SimpleNamespace(status="complete", customer="cus_123"),
    )

    async def fake_sync(customer_id, db):
        return {
            "status": "active",
            "organization_id": org.id,
            "seats": 8,
        }

    monkeypatch.setattr(service, "sync_stripe_to_postgres", fake_sync)

    result = await sync_after_checkout("cs_test_123", "user-1", db)

    assert result["status"] == "active"
    assert result["organization_id"] == org.id
