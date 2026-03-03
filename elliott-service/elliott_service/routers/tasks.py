from fastapi import APIRouter, Depends, HTTPException

from elliott_service.auth import verify_token
from elliott_service.models import ApiResponse
from elliott_service.routers.bugs import task_mgr

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"], dependencies=[Depends(verify_token)])


@router.get("/{task_id}", response_model=ApiResponse)
async def get_task(task_id: str):
    """Poll the result of an async task."""
    result = task_mgr.get_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return result
