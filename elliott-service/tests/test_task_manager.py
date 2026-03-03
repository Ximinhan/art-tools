import asyncio

import pytest

from elliott_service.task_manager import TaskManager


@pytest.mark.asyncio
async def test_execute_fast_task_returns_completed():
    """A fast task should return completed status synchronously."""
    tm = TaskManager()

    async def fast_work():
        return {"bugs": ["BUG-1"]}

    result = await tm.execute_with_timeout(fast_work, timeout=5)
    assert result["status"] == "completed"
    assert result["data"] == {"bugs": ["BUG-1"]}


@pytest.mark.asyncio
async def test_execute_slow_task_returns_pending():
    """A slow task should return pending status with task_id."""
    tm = TaskManager()

    async def slow_work():
        await asyncio.sleep(10)
        return {"bugs": ["BUG-1"]}

    result = await tm.execute_with_timeout(slow_work, timeout=0.1)
    assert result["status"] == "pending"
    assert "task_id" in result


@pytest.mark.asyncio
async def test_get_task_result_after_completion():
    """Should be able to retrieve result after async task completes."""
    tm = TaskManager()

    async def quick_work():
        await asyncio.sleep(0.1)
        return {"bugs": ["BUG-1"]}

    result = await tm.execute_with_timeout(quick_work, timeout=0.01)
    task_id = result["task_id"]

    await asyncio.sleep(0.3)

    task_result = tm.get_task(task_id)
    assert task_result["status"] == "completed"
    assert task_result["data"] == {"bugs": ["BUG-1"]}


@pytest.mark.asyncio
async def test_get_task_error_sync():
    """Should capture errors from tasks that fail before timeout."""
    tm = TaskManager()

    async def failing_work():
        raise ValueError("something broke")

    result = await tm.execute_with_timeout(failing_work, timeout=5)
    assert result["status"] == "error"
    assert "something broke" in result["error"]


@pytest.mark.asyncio
async def test_get_task_error_async():
    """Should capture errors from tasks that fail after timeout."""
    tm = TaskManager()

    async def slow_failing_work():
        await asyncio.sleep(0.1)
        raise ValueError("async failure")

    result = await tm.execute_with_timeout(slow_failing_work, timeout=0.01)
    task_id = result["task_id"]

    await asyncio.sleep(0.3)
    task_result = tm.get_task(task_id)
    assert task_result["status"] == "error"
    assert "async failure" in task_result["error"]


def test_get_unknown_task():
    tm = TaskManager()
    result = tm.get_task("nonexistent")
    assert result is None
