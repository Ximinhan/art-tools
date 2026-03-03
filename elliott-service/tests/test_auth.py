import pytest
from httpx import ASGITransport, AsyncClient

from elliott_service.main import app


@pytest.mark.asyncio
async def test_health_no_auth_required():
    """Health endpoint should not require authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_no_token(monkeypatch):
    """Protected endpoints should return 401 without a valid token."""
    monkeypatch.setattr("elliott_service.config.settings.api_token", "secret-token")
    monkeypatch.setattr("elliott_service.auth.settings.api_token", "secret-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/bugs/find", params={"group": "openshift-4.18"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_accepts_valid_token(monkeypatch):
    """Protected endpoints should accept valid Bearer token."""
    monkeypatch.setattr("elliott_service.config.settings.api_token", "secret-token")
    monkeypatch.setattr("elliott_service.auth.settings.api_token", "secret-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/bugs/find",
            params={"group": "openshift-4.18"},
            headers={"Authorization": "Bearer secret-token"},
        )
    assert resp.status_code != 401
