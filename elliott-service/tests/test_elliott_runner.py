from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from elliott_service.elliott_runner import ElliottRunner


@pytest.mark.asyncio
@patch("elliott_service.elliott_runner.Runtime")
@patch("elliott_service.elliott_runner.Config")
async def test_find_bugs_returns_dict(mock_config_cls, mock_runtime_cls):
    """find_bugs should return a dict of advisory_kind -> bug_id list."""
    mock_runtime = MagicMock()
    mock_runtime_cls.return_value = mock_runtime
    mock_runtime.get_major_minor.return_value = (4, 18)
    mock_runtime.get_bug_tracker.return_value = MagicMock()
    mock_runtime.remove_tmp_working_dir = False

    mock_config = MagicMock()
    mock_config.to_dict.return_value = {"group": "openshift-4.18", "assembly": "stream"}
    mock_config_cls.return_value = mock_config

    mock_bug = MagicMock()
    mock_bug.id = "OCPBUGS-123"
    mock_bug.summary = "test bug"
    mock_bug.status = "MODIFIED"
    mock_bug.component = "networking"
    mock_bug.target_release = ["4.18.0"]

    with (
        patch("elliott_service.elliott_runner.get_bugs_sweep", new_callable=AsyncMock, return_value=[mock_bug]),
        patch("elliott_service.elliott_runner.get_assembly_bug_ids", return_value=(set(), set())),
        patch("elliott_service.elliott_runner.get_builds_by_advisory_kind", return_value={}),
        patch(
            "elliott_service.elliott_runner.categorize_bugs_by_type",
            return_value=({"image": {mock_bug}}, []),
        ),
    ):
        runner = ElliottRunner(
            data_path="https://github.com/openshift-eng/ocp-build-data",
            working_dir="/tmp/test",
        )
        result = await runner.find_bugs(group="openshift-4.18", assembly="stream")

    assert "image" in result
    assert len(result["image"]) == 1
    assert result["image"][0]["id"] == "OCPBUGS-123"
    assert result["image"][0]["summary"] == "test bug"


@pytest.mark.asyncio
@patch("elliott_service.elliott_runner.Runtime")
@patch("elliott_service.elliott_runner.Config")
async def test_find_bugs_empty_result(mock_config_cls, mock_runtime_cls):
    """find_bugs should return empty dict when no bugs found."""
    mock_runtime = MagicMock()
    mock_runtime_cls.return_value = mock_runtime
    mock_runtime.get_major_minor.return_value = (4, 18)
    mock_runtime.get_bug_tracker.return_value = MagicMock()
    mock_runtime.remove_tmp_working_dir = False

    mock_config = MagicMock()
    mock_config.to_dict.return_value = {"group": "openshift-4.18", "assembly": "stream"}
    mock_config_cls.return_value = mock_config

    with (
        patch("elliott_service.elliott_runner.get_bugs_sweep", new_callable=AsyncMock, return_value=[]),
        patch("elliott_service.elliott_runner.get_assembly_bug_ids", return_value=(set(), set())),
        patch("elliott_service.elliott_runner.get_builds_by_advisory_kind", return_value={}),
        patch("elliott_service.elliott_runner.categorize_bugs_by_type", return_value=({}, [])),
    ):
        runner = ElliottRunner(
            data_path="https://github.com/openshift-eng/ocp-build-data",
            working_dir="/tmp/test",
        )
        result = await runner.find_bugs(group="openshift-4.18", assembly="stream")

    assert result == {}
