from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import AuthContext, require_admin, require_owner_membership
from app.main import app
from app.organization.router import get_db_session


@pytest.fixture
async def api_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def make_owner_context(org_id: str = "org-1") -> AuthContext:
    user = SimpleNamespace(
        id="owner-user-id",
        email="owner@example.com",
        first_name="Owner",
        last_name="User",
        daily_token_limit=500000,
        user_metadata=SimpleNamespace(first_name="Owner", last_name="User"),
        app_metadata=SimpleNamespace(is_admin=False, daily_token_limit=500000),
        is_authenticated=True,
    )
    organization = SimpleNamespace(
        id=org_id,
        name="Acme",
        max_users=5,
        subscription_status="active",
    )
    membership = SimpleNamespace(role="owner", organization_id=org_id)
    return AuthContext(
        user=user, organization=organization, membership=membership, subscription=None
    )


@pytest.mark.asyncio
async def test_get_organization_rejects_access_to_other_owners_org(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context(org_id="org-1")

    async def override_db():
        yield SimpleNamespace()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("route should reject before querying another organization")

    app.dependency_overrides[require_owner_membership] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_organization_by_id", fail_if_called)

    response = await api_client.get("/api/v1/organization/organizations/org-2")

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization access denied"


@pytest.mark.asyncio
async def test_update_organization_rejects_access_to_other_owners_org(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context(org_id="org-1")

    async def override_db():
        yield SimpleNamespace()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("route should reject before updating another organization")

    app.dependency_overrides[require_owner_membership] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "update_organization_service", fail_if_called)

    response = await api_client.put(
        "/api/v1/organization/organizations/org-2",
        json={"max_users": 10},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization access denied"


@pytest.mark.asyncio
async def test_update_user_rejects_members_from_other_organizations(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context(org_id="org-1")

    async def override_db():
        yield SimpleNamespace()

    async def fake_membership(db, user_id):
        return SimpleNamespace(organization_id="org-2")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("token limit should not update for another organization")

    app.dependency_overrides[require_owner_membership] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_membership_for_user", fake_membership)
    monkeypatch.setattr(router, "update_user_token_limit", fail_if_called)

    response = await api_client.put(
        "/api/v1/organization/users/user-2",
        json={"daily_token_limit": 12345},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found in organization"


@pytest.mark.asyncio
async def test_admin_create_organization_passes_requested_owner_id_to_service(
    api_client, monkeypatch
):
    from app.organization import router

    async def override_admin():
        return SimpleNamespace(id="admin-user-id", email="admin@example.com")

    async def override_db():
        yield SimpleNamespace()

    captured = {}

    async def fake_get_user_by_id(user_id):
        return SimpleNamespace(id=user_id, email="owner@example.com")

    async def fake_get_membership_for_user(db, user_id):
        return None

    async def fake_create_organization_service(db, name, max_users):
        captured["call"] = {
            "name": name,
            "max_users": max_users,
        }
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id="org-1",
            name=name,
            max_users=max_users,
            created_at=now,
            updated_at=now,
        )

    async def fake_add_user_to_organization(db, org_id, user_id, role):
        captured["membership"] = {"org_id": org_id, "user_id": user_id, "role": role}
        return SimpleNamespace()

    app.dependency_overrides[require_admin] = override_admin
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr(router, "get_membership_for_user", fake_get_membership_for_user)
    monkeypatch.setattr(router, "create_organization_service", fake_create_organization_service)
    monkeypatch.setattr(router, "add_user_to_organization", fake_add_user_to_organization)

    response = await api_client.post(
        "/api/v1/organization/organizations",
        json={"name": "Acme", "max_users": 25, "owner_id": "owner-user-id"},
    )

    assert response.status_code == 201
    assert captured["call"] == {
        "name": "Acme",
        "max_users": 25,
    }
    assert captured["membership"] == {
        "org_id": "org-1",
        "user_id": "owner-user-id",
        "role": "owner",
    }
    assert response.json()["id"] == "org-1"
    assert response.json()["active_user_count"] == 1


@pytest.mark.asyncio
async def test_admin_create_organization_requires_explicit_owner_id(api_client):
    async def override_admin():
        return SimpleNamespace(id="admin-user-id", email="admin@example.com")

    async def override_db():
        yield SimpleNamespace()

    app.dependency_overrides[require_admin] = override_admin
    app.dependency_overrides[get_db_session] = override_db

    response = await api_client.post(
        "/api/v1/organization/organizations",
        json={"name": "Acme", "max_users": 25},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_create_organization_rejects_unknown_owner_id(api_client, monkeypatch):
    from app.organization import router

    async def override_admin():
        return SimpleNamespace(id="admin-user-id", email="admin@example.com")

    async def override_db():
        yield SimpleNamespace()

    async def fake_get_user_by_id(user_id):
        return None

    app.dependency_overrides[require_admin] = override_admin
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_user_by_id", fake_get_user_by_id)

    response = await api_client.post(
        "/api/v1/organization/organizations",
        json={"name": "Acme", "max_users": 25, "owner_id": "missing-user"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Owner user not found"
