import json
import time

import redis.asyncio as redis

from app.config import settings

# A location shared hours ago may no longer be where the user actually is.
LOCATION_TTL_SECONDS = 12 * 60 * 60

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def _location_key(chat_id: int) -> str:
    return f"lifeos:location:{chat_id}"


async def set_location(chat_id: int, lat: float, lon: float) -> None:
    payload = json.dumps({"lat": lat, "lon": lon, "ts": time.time()})
    await _get_client().set(_location_key(chat_id), payload, ex=LOCATION_TTL_SECONDS)


async def get_location(chat_id: int) -> tuple[float, float] | None:
    raw = await _get_client().get(_location_key(chat_id))
    if raw is None:
        return None
    data = json.loads(raw)
    return data["lat"], data["lon"]


# Google's access tokens expire in 1h; cache just under that so we're not
# hitting the token endpoint on every calendar call.
GOOGLE_ACCESS_TOKEN_TTL_SECONDS = 50 * 60
_GOOGLE_ACCESS_TOKEN_KEY = "lifeos:google_calendar_access_token"


async def get_cached_access_token() -> str | None:
    return await _get_client().get(_GOOGLE_ACCESS_TOKEN_KEY)


async def set_cached_access_token(token: str) -> None:
    await _get_client().set(
        _GOOGLE_ACCESS_TOKEN_KEY, token, ex=GOOGLE_ACCESS_TOKEN_TTL_SECONDS
    )


# --- Chat event pub/sub (webapp real-time push for scheduler messages) ---

CHAT_EVENTS_CHANNEL = "lifeos:chat_events"


async def publish_chat_event(session_id: int, message: dict) -> None:
    payload = json.dumps({"session_id": session_id, "message": message})
    await _get_client().publish(CHAT_EVENTS_CHANNEL, payload)


async def publish_status_event(session_id: int, status: str) -> None:
    """Live "what's happening right now" pings for the webapp while a turn
    is in flight (transcribing / thinking locally / consulting the cloud
    model) — same channel as publish_chat_event, distinguished on the
    frontend by having a "status" key instead of "message"."""
    payload = json.dumps({"session_id": session_id, "status": status})
    await _get_client().publish(CHAT_EVENTS_CHANNEL, payload)


async def subscribe_chat_events(poll_timeout: float = 15.0):
    """Yields decoded {"session_id", "message"} dicts as they're published,
    or None on each poll_timeout with nothing new — lets the SSE endpoint
    send a keepalive so idle connections (the gap between morning/evening
    briefs is hours) don't get dropped by a proxy. Runs until the caller
    stops iterating (e.g. the SSE client disconnects) — each call gets its
    own pubsub connection."""
    pubsub = _get_client().pubsub()
    await pubsub.subscribe(CHAT_EVENTS_CHANNEL)
    try:
        while True:
            raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_timeout)
            if raw is None:
                yield None
                continue
            yield json.loads(raw["data"])
    finally:
        await pubsub.unsubscribe(CHAT_EVENTS_CHANNEL)
        await pubsub.aclose()
