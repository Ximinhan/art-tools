from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    status: str  # "completed", "pending", "error"
    data: Any | None = None
    task_id: str | None = None
    poll_url: str | None = None
    error: str | None = None
    detail: str | None = None
    elapsed_seconds: float | None = None
