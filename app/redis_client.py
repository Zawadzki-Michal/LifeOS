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
