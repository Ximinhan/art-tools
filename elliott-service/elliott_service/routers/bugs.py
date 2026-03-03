from fastapi import APIRouter, Depends, Query

from elliott_service.auth import verify_token
from elliott_service.config import settings
from elliott_service.elliott_runner import ElliottRunner
from elliott_service.models import ApiResponse
from elliott_service.task_manager import TaskManager

router = APIRouter(prefix="/api/v1/bugs", tags=["bugs"], dependencies=[Depends(verify_token)])

runner = ElliottRunner(
    data_path=settings.elliott_data_path,
    working_dir=settings.elliott_working_dir,
)
task_mgr = TaskManager()


@router.get("/find", response_model=ApiResponse)
async def find_bugs(
    group: str = Query(..., description="OCP group, e.g. openshift-4.18"),
    assembly: str = Query("stream", description="Assembly name"),
    exclude_trackers: bool = Query(False, description="Exclude tracker bugs"),
    permissive: bool = Query(False, description="Ignore invalid bugs"),
    cve_only: bool = Query(False, description="Only find CVE trackers"),
    timeout: int = Query(None, description="Timeout in seconds (default from config)"),
):
    """Find OCP bugs eligible for the given group and assembly."""
    t = timeout or settings.default_timeout

    async def work():
        return await runner.find_bugs(
            group=group,
            assembly=assembly,
            exclude_trackers=exclude_trackers,
            permissive=permissive,
            cve_only=cve_only,
        )

    result = await task_mgr.execute_with_timeout(work, timeout=t)
    if result.get("task_id"):
        result["poll_url"] = f"/api/v1/tasks/{result['task_id']}"
    return result
