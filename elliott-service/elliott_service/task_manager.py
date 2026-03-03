import asyncio
import time
import traceback
from typing import Any, Awaitable, Callable
from uuid import uuid4


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}

    async def execute_with_timeout(
        self,
        func: Callable[[], Awaitable[Any]],
        timeout: float = 120,
    ) -> dict[str, Any]:
        """Execute an async function with timeout.

        If the function completes within the timeout, return the result directly.
        If it times out, schedule it as a background task and return a task_id.
        If it raises before the timeout, capture the error and return it.
        """
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(func(), timeout=timeout)
            elapsed = time.monotonic() - start
            return {
                "status": "completed",
                "data": result,
                "elapsed_seconds": round(elapsed, 2),
            }
        except asyncio.TimeoutError:
            task_id = str(uuid4())
            self._tasks[task_id] = {"status": "pending", "started_at": start}
            asyncio.create_task(self._run_and_store(task_id, func, start))
            return {
                "status": "pending",
                "task_id": task_id,
            }
        except Exception as e:
            elapsed = time.monotonic() - start
            return {
                "status": "error",
                "error": str(e),
                "detail": traceback.format_exc(),
                "elapsed_seconds": round(elapsed, 2),
            }

    async def _run_and_store(
        self,
        task_id: str,
        func: Callable[[], Awaitable[Any]],
        start: float,
    ):
        try:
            result = await func()
            elapsed = time.monotonic() - start
            self._tasks[task_id] = {
                "status": "completed",
                "data": result,
                "elapsed_seconds": round(elapsed, 2),
            }
        except Exception as e:
            elapsed = time.monotonic() - start
            self._tasks[task_id] = {
                "status": "error",
                "error": str(e),
                "detail": traceback.format_exc(),
                "elapsed_seconds": round(elapsed, 2),
            }

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)
