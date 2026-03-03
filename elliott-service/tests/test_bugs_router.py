from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from elliott_service.main import app


@pytest.mark.asyncio
@patch("elliott_service.routers.bugs.runner")
async def test_find_bugs_returns_results(mock_runner):
    """find-bugs endpoint should return categorized bugs."""
    mock_runner.find_bugs = AsyncMock(
        return_value={
            "image": [{"id": "OCPBUGS-1", "summary": "bug 1", "status": "MODIFIED"}],
            "rpm": [{"id": "OCPBUGS-2", "summary": "bug 2", "status": "ON_QA"}],
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/bugs/find", params={"group": "openshift-4.18"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "image" in data["data"]
    assert len(data["data"]["image"]) == 1


@pytest.mark.asyncio
async def test_find_bugs_missing_group():
    """find-bugs endpoint should return 422 if group is missing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/bugs/find")
    assert resp.status_code == 422
