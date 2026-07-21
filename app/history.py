import json

import redis.asyncio as redis

from app.config import settings

TTL_SECONDS = 6 * 60 * 60
MAX_TURNS = 10

_redis = redis.from_url(settings.redis_url, decode_responses=True)


def _key(chat_id: int) -> str:
    return f"chat_history:{chat_id}"


async def get_history(chat_id: int) -> list[dict]:
    raw = await _redis.get(_key(chat_id))
    return json.loads(raw) if raw else []


async def append_history(chat_id: int, user_text: str, assistant_text: str) -> None:
    history = await get_history(chat_id)
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    history = history[-(MAX_TURNS * 2):]
    await _redis.set(_key(chat_id), json.dumps(history), ex=TTL_SECONDS)


async def clear_history(chat_id: int) -> None:
    await _redis.delete(_key(chat_id))
