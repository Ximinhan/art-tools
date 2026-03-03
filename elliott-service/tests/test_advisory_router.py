from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from elliott_service.main import app


@pytest.mark.asyncio
@patch("elliott_service.routers.advisory.Advisory")
async def test_get_advisory(mock_advisory_cls):
    """Should return advisory details."""
    mock_adv = MagicMock()
    mock_adv.errata_id = 12345
    mock_adv.errata_state = "QE"
    mock_adv.synopsis = "OpenShift 4.18 image release"
    mock_adv.publish_date_override = "2026-03-15"
    mock_adv.url.return_value = "https://errata.devel.redhat.com/advisory/12345"
    mock_adv.errata_bugs = [{"id": 1}]
    mock_adv.jira_issues = ["OCPBUGS-1"]
    mock_adv.errata_builds = {"tag": ["build-1.0-1.el8"]}
    mock_advisory_cls.return_value = mock_adv

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/advisory/12345")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["data"]["errata_id"] == 12345
    assert data["data"]["errata_state"] == "QE"
    assert data["data"]["url"] == "https://errata.devel.redhat.com/advisory/12345"
