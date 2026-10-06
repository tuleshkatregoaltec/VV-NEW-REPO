from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.router import get_db_session, require_auth
from app.main import app


class FakeDB:
    def __init__(self, organization=None):
        self.organization = organization

    async def get(self, model, key):
        return self.organization


def make_user(**overrides):
    user = SimpleNamespace(
        id="user-1",
        email="owner@example.com",
        first_name="Ada",
        last_name="Lovelace",
        daily_token_limit=500000,
        user_metadata=SimpleNamespace(first_name="Ada", last_name="Lovelace"),
        app_metadata=SimpleNamespace(is_admin=False, daily_token_limit=500000),
        is_authenticated=True,
        is_admin=False,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


@pytest.fixture
async def api_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_me_returns_owner_subscription_context(api_client, monkeypatch):
    from app.auth import router

    async def override_require_auth():
        return make_user()

    async def override_db():
        yield FakeDB(
            organization=SimpleNamespace(id="org-1", name="Acme", subscription_status="trialing")
        )

    async def fake_membership(db, user_id):
        return SimpleNamespace(organization_id="org-1", role="owner")

    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router.organization_service, "get_membership_for_user", fake_membership)
    response = await api_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-1",
        "email": "owner@example.com",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "avatar_url": None,
        "organization_id": "org-1",
        "organization_name": "Acme",
        "role": "owner",
        "is_owner": True,
        "subscription_status": "trialing",
    }


@pytest.mark.asyncio
async def test_me_promotes_system_admin_role(api_client, monkeypatch):
    from app.auth import router

    async def override_require_auth():
        return make_user(email="admin@example.com", is_admin=True)

    async def override_db():
        yield FakeDB(organization=None)

    async def fake_membership(db, user_id):
        return None

    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router.organization_service, "get_membership_for_user", fake_membership)
    response = await api_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["organization_id"] is None
