from fastapi import HTTPException, Request

from elliott_service.config import settings


async def verify_token(request: Request):
    """Verify Bearer token from Authorization header.

    Skips verification if no ELLIOTT_API_TOKEN is configured (dev mode).
    """
    if not settings.api_token:
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header.removeprefix("Bearer ").strip()
    if token != settings.api_token:
        raise HTTPException(status_code=401, detail="Invalid token")
