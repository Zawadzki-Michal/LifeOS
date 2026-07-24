"""Server-Sent Events endpoint so the web app sees proactive scheduler
messages (morning/evening briefs, bill reminders) the instant they're sent,
instead of only on next page load. See app.scheduler._broadcast_to_web and
app.redis_client's chat-event pub/sub. Hand-rolled SSE via StreamingResponse
rather than adding a new dependency — it's a handful of lines."""

import json

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app import redis_client
from app.auth import require_auth

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.get("/stream")
async def stream(request: Request):
    async def event_generator():
        async for event in redis_client.subscribe_chat_events():
            if await request.is_disconnected():
                break
            if event is None:
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
