from fastapi import APIRouter, Depends

from elliott_service.auth import verify_token
from elliott_service.models import ApiResponse

try:
    from elliottlib.errata import Advisory
except ImportError:
    Advisory = None  # Will be mocked in tests

router = APIRouter(prefix="/api/v1/advisory", tags=["advisory"], dependencies=[Depends(verify_token)])


@router.get("/{advisory_id}", response_model=ApiResponse)
async def get_advisory(advisory_id: int):
    """Get details about a specific advisory."""
    adv = Advisory(errata_id=advisory_id)
    data = {
        "errata_id": adv.errata_id,
        "errata_state": adv.errata_state,
        "synopsis": adv.synopsis,
        "publish_date": adv.publish_date_override,
        "url": adv.url(),
        "bugs": adv.errata_bugs,
        "jira_issues": adv.jira_issues,
        "builds": adv.errata_builds,
    }
    return ApiResponse(status="completed", data=data)
