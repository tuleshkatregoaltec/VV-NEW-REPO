import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import require_admin
from app.main import app


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
async def test_admin_endpoint_rejects_unauthenticated_user(api_client):
    response = await api_client.get("/api/v1/admin/organizations")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_rejects_non_admin_user(api_client):
    async def reject_non_admin():
        raise HTTPException(status_code=403, detail="System admin access required")

    app.dependency_overrides[require_admin] = reject_non_admin

    response = await api_client.get("/api/v1/admin/organizations")

    assert response.status_code == 403
    assert response.json()["detail"] == "System admin access required"
