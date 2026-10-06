from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import (
    AuthContext,
    require_active_owner,
    require_auth,
    require_owner_membership,
)
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


def make_owner_context(max_users: int = 3, org_id: str = "org-1") -> AuthContext:
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
        max_users=max_users,
        subscription_status="active",
    )
    membership = SimpleNamespace(role="owner", organization_id=org_id)
    return AuthContext(
        user=user, organization=organization, membership=membership, subscription=None
    )


@pytest.mark.asyncio
async def test_invite_user_returns_created_invitation_token(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context()

    async def override_db():
        yield SimpleNamespace()

    captured = {}

    async def fake_member_count(db, organization_id):
        return 1

    async def fake_expire_pending(db, organization_id, email, exclude_token=None):
        captured["expired"] = {
            "organization_id": organization_id,
            "email": email,
            "exclude_token": exclude_token,
        }
        return 1

    async def fake_create_invitation(db, organization_id, email, invited_by_user_id, role):
        captured["invitation"] = {
            "organization_id": organization_id,
            "email": email,
            "invited_by_user_id": invited_by_user_id,
            "role": role,
        }
        return SimpleNamespace(token="invite-token")

    async def fake_send_magic_link(email, redirect_url, should_create_user=True):
        captured["delivery"] = {
            "email": email,
            "redirect_url": redirect_url,
            "should_create_user": should_create_user,
        }
        return {"success": True, "error": None}

    async def fake_pending_invitation_count(db, organization_id):
        return 0

    app.dependency_overrides[require_active_owner] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_member_count", fake_member_count)
    monkeypatch.setattr(router, "get_pending_invitation_count", fake_pending_invitation_count)
    monkeypatch.setattr(router, "expire_pending_invitations", fake_expire_pending)
    monkeypatch.setattr(router, "create_invitation", fake_create_invitation)
    monkeypatch.setattr(router, "send_magic_link_email", fake_send_magic_link)
    monkeypatch.setattr(router.settings, "FRONTEND_URL", "http://localhost:5173")

    response = await api_client.post(
        "/api/v1/organization/invite-user",
        json={
            "email": "member@example.com",
        },
    )

    assert response.status_code == 200
    assert captured["expired"] == {
        "organization_id": "org-1",
        "email": "member@example.com",
        "exclude_token": "invite-token",
    }
    assert captured["invitation"] == {
        "organization_id": "org-1",
        "email": "member@example.com",
        "invited_by_user_id": "owner-user-id",
        "role": "member",
    }
    assert captured["delivery"] == {
        "email": "member@example.com",
        "redirect_url": "http://localhost:5173/invite?token=invite-token",
        "should_create_user": True,
    }
    assert response.json() == {
        "success": True,
        "invitation_token": "invite-token",
    }


@pytest.mark.asyncio
async def test_invite_user_rejects_when_org_has_no_available_seats(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context(max_users=1)

    async def override_db():
        yield SimpleNamespace()

    async def fake_member_count(db, organization_id):
        return 1

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("create_invitation should not be called when seats are exhausted")

    async def fake_pending_invitation_count(db, organization_id):
        return 0

    app.dependency_overrides[require_active_owner] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_member_count", fake_member_count)
    monkeypatch.setattr(router, "get_pending_invitation_count", fake_pending_invitation_count)
    monkeypatch.setattr(router, "expire_pending_invitations", fail_if_called)
    monkeypatch.setattr(router, "create_invitation", fail_if_called)

    response = await api_client.post(
        "/api/v1/organization/invite-user",
        json={
            "email": "member@example.com",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Organization has reached maximum seat limit (1) including pending invitations"
    )


@pytest.mark.asyncio
async def test_invite_user_rejects_when_pending_invites_have_reserved_remaining_seats(
    api_client, monkeypatch
):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context(max_users=3)

    async def override_db():
        yield SimpleNamespace()

    async def fake_member_count(db, organization_id):
        return 2

    async def fake_pending_invitation_count(db, organization_id):
        return 1

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("create_invitation should not be called when seats are exhausted")

    app.dependency_overrides[require_active_owner] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_member_count", fake_member_count)
    monkeypatch.setattr(router, "get_pending_invitation_count", fake_pending_invitation_count)
    monkeypatch.setattr(router, "expire_pending_invitations", fail_if_called)
    monkeypatch.setattr(router, "create_invitation", fail_if_called)

    response = await api_client.post(
        "/api/v1/organization/invite-user",
        json={"email": "member@example.com"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Organization has reached maximum seat limit (3) including pending invitations"
    )


@pytest.mark.asyncio
async def test_invite_user_expires_new_token_when_delivery_fails(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context()

    class FakeDB:
        def __init__(self):
            self.saved = []
            self.commits = 0

        def add(self, item):
            self.saved.append(item)

        async def commit(self):
            self.commits += 1

    db = FakeDB()

    async def override_db():
        yield db

    async def fake_member_count(db, organization_id):
        return 1

    async def fake_expire_pending(db, organization_id, email, exclude_token=None):
        return 0

    invitation = SimpleNamespace(token="invite-token", status="pending")

    async def fake_create_invitation(db, organization_id, email, invited_by_user_id, role):
        return invitation

    async def fake_send_magic_link(email, redirect_url, should_create_user=True):
        return {"success": False, "error": "mailer unavailable"}

    async def fake_pending_invitation_count(db, organization_id):
        return 0

    app.dependency_overrides[require_active_owner] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_member_count", fake_member_count)
    monkeypatch.setattr(router, "get_pending_invitation_count", fake_pending_invitation_count)
    monkeypatch.setattr(router, "expire_pending_invitations", fake_expire_pending)
    monkeypatch.setattr(router, "create_invitation", fake_create_invitation)
    monkeypatch.setattr(router, "send_magic_link_email", fake_send_magic_link)
    monkeypatch.setattr(router.settings, "FRONTEND_URL", "http://localhost:5173")

    response = await api_client.post(
        "/api/v1/organization/invite-user",
        json={
            "email": "member@example.com",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "mailer unavailable"
    assert invitation.status == "expired"
    assert db.saved == [invitation]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_invite_user_expires_prior_pending_tokens_only_after_success(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context()

    async def override_db():
        yield SimpleNamespace()

    call_order = []

    async def fake_member_count(db, organization_id):
        call_order.append("seat-check")
        return 1

    async def fake_create_invitation(db, organization_id, email, invited_by_user_id, role):
        call_order.append("create")
        return SimpleNamespace(token="invite-token")

    async def fake_send_magic_link(email, redirect_url, should_create_user=True):
        call_order.append("send")
        return {"success": True, "error": None}

    async def fake_expire_pending(db, organization_id, email, exclude_token=None):
        call_order.append("expire")
        return 1

    async def fake_pending_invitation_count(db, organization_id):
        return 0

    app.dependency_overrides[require_active_owner] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_member_count", fake_member_count)
    monkeypatch.setattr(router, "get_pending_invitation_count", fake_pending_invitation_count)
    monkeypatch.setattr(router, "create_invitation", fake_create_invitation)
    monkeypatch.setattr(router, "send_magic_link_email", fake_send_magic_link)
    monkeypatch.setattr(router, "expire_pending_invitations", fake_expire_pending)
    monkeypatch.setattr(router.settings, "FRONTEND_URL", "http://localhost:5173")

    response = await api_client.post(
        "/api/v1/organization/invite-user",
        json={"email": "member@example.com"},
    )

    assert response.status_code == 200
    assert call_order == ["seat-check", "create", "send", "expire"]


@pytest.mark.asyncio
async def test_validate_invite_token_rejects_non_pending_invitation(api_client, monkeypatch):
    from app.organization import router

    async def override_db():
        yield SimpleNamespace()

    async def fake_get_invitation_by_token(db, token):
        return SimpleNamespace(status="expired", expires_at=None)

    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_invitation_by_token", fake_get_invitation_by_token)

    response = await api_client.get("/api/v1/organization/validate-invite-token?token=dead-token")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invitation is no longer valid"


@pytest.mark.asyncio
async def test_delete_invitation_cancels_pending_invite(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context()

    async def override_db():
        yield SimpleNamespace()

    invitation = SimpleNamespace(
        id="invite-1",
        organization_id="org-1",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    captured = {}

    async def fake_get_invitation_by_id(db, invitation_id):
        return invitation

    async def fake_cancel_invitation(db, invitation_record):
        captured["invitation_id"] = invitation_record.id
        invitation_record.status = "declined"
        return invitation_record

    app.dependency_overrides[require_owner_membership] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_invitation_by_id", fake_get_invitation_by_id)
    monkeypatch.setattr(router, "cancel_invitation", fake_cancel_invitation)

    response = await api_client.delete("/api/v1/organization/invitations/invite-1")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert captured["invitation_id"] == "invite-1"


@pytest.mark.asyncio
async def test_delete_invitation_rejects_other_organization_invite(api_client, monkeypatch):
    from app.organization import router

    async def override_owner_context():
        return make_owner_context(org_id="org-1")

    async def override_db():
        yield SimpleNamespace()

    invitation = SimpleNamespace(
        id="invite-1",
        organization_id="org-2",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    async def fake_get_invitation_by_id(db, invitation_id):
        return invitation

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("cancel_invitation should not be called for another org")

    app.dependency_overrides[require_owner_membership] = override_owner_context
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(router, "get_invitation_by_id", fake_get_invitation_by_id)
    monkeypatch.setattr(router, "cancel_invitation", fail_if_called)

    response = await api_client.delete("/api/v1/organization/invitations/invite-1")

    assert response.status_code == 404
    assert response.json()["detail"] == "Invitation not found"


@pytest.mark.asyncio
async def test_accept_invite_rejects_when_org_has_no_seats_left(api_client, monkeypatch):
    from app.organization import router

    async def override_require_auth():
        return SimpleNamespace(id="user-2", email="member@example.com")

    async def override_db():
        yield SimpleNamespace()

    invitation = SimpleNamespace(
        organization_id="org-1",
        email="member@example.com",
        role="member",
    )
    organization = SimpleNamespace(id="org-1", name="Acme", max_users=1)

    async def fake_get_pending_invitation_or_error(db, token):
        return invitation

    async def fake_existing_membership(db, user_id):
        return None

    async def fake_get_organization_by_id(db, org_id):
        return organization

    async def fake_get_member_count(db, org_id):
        return 1

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("membership should not be created when the org is full")

    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr(
        router, "get_pending_invitation_or_error", fake_get_pending_invitation_or_error
    )
    monkeypatch.setattr(router, "get_membership_for_user", fake_existing_membership)
    monkeypatch.setattr(router, "get_organization_by_id", fake_get_organization_by_id)
    monkeypatch.setattr(router, "get_member_count", fake_get_member_count)
    monkeypatch.setattr(router, "add_user_to_organization", fail_if_called)
    monkeypatch.setattr(router, "mark_invitation_accepted", fail_if_called)

    response = await api_client.post(
        "/api/v1/organization/accept-invite",
        json={"token": "invite-token"},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "This organization has no available seats left for this invitation."
    )
