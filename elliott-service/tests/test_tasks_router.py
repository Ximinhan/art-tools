from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from elliott_service.main import app


@pytest.mark.asyncio
async def test_get_task_not_found():
    """Should return 404 for unknown task_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/tasks/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
@patch("elliott_service.routers.tasks.task_mgr")
async def test_get_task_completed(mock_mgr):
    """Should return completed task data."""
    mock_mgr.get_task.return_value = {
        "status": "completed",
        "data": {"bugs": []},
        "elapsed_seconds": 5.0,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/tasks/abc-123")

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
