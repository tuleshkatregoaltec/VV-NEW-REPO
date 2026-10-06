from functools import lru_cache
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import AuthContext, require_active_subscription


@lru_cache(maxsize=1)
def get_app():
    from app.main import app

    return app


def make_mock_auth_context() -> AuthContext:
    user = make_current_user()

    org = MagicMock()
    org.id = 1
    org.subscription_status = "active"

    membership = MagicMock()
    membership.role = "owner"
    membership.organization_id = 1

    return AuthContext(user=user, organization=org, membership=membership, subscription=None)


def make_current_user(**overrides):
    user = SimpleNamespace(
        id="test-user-id",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        daily_token_limit=500000,
        user_metadata=SimpleNamespace(first_name="Test", last_name="User"),
        app_metadata=SimpleNamespace(is_admin=False, daily_token_limit=500000),
        is_authenticated=True,
    )

    for key, value in overrides.items():
        setattr(user, key, value)

    return user


@pytest.fixture
def mock_auth():
    """Override require_active_subscription with a mock auth context."""
    app = get_app()
    app.dependency_overrides[require_active_subscription] = lambda: make_mock_auth_context()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(mock_auth):
    """Authenticated AsyncClient for router tests."""
    app = get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def client_no_auth():
    """Unauthenticated AsyncClient for testing auth enforcement."""
    app = get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
