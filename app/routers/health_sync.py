import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from app import health_client
from app.config import settings

logger = logging.getLogger("lifeos.health_sync")

router = APIRouter()


@router.post("/apple-health/sync")
async def apple_health_sync(request: Request, authorization: str = Header(default="")):
    expected = f"Bearer {settings.health_sync_token}"
    if not settings.health_sync_token or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    try:
        result = await health_client.ingest_payload(payload)
    except Exception:
        logger.exception("Failed to ingest Apple Health payload")
        raise HTTPException(status_code=400, detail="Failed to parse payload")

    return {"status": "ok", "detail": result}
