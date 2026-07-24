"""Cloud reasoning path for open-ended requests (meal proposals, health
advice) local Qwen isn't well-suited for — see consult_advanced_model in
app/tools.py. Mirrors app/ollama_client.py's chat() return shape
({content, prompt_tokens, completion_tokens}) so chat_service.py doesn't need
to special-case which model answered.
"""

import httpx

from app.config import settings

API_URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_URL = "https://openrouter.ai/api/v1/key"
CREDITS_URL = "https://openrouter.ai/api/v1/credits"


async def chat(messages: list[dict], model: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            API_URL,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={"model": model or settings.openrouter_model, "messages": messages},
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        return {
            "content": data["choices"][0]["message"]["content"],
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }


async def get_key_usage() -> dict:
    """Real spend for this API key, straight from OpenRouter — not our own
    interaction_log estimate. usage_daily/weekly/monthly reset on UTC
    day/week(Mon)/month boundaries; limit/limit_remaining are null when the
    key has no cap configured (the case today)."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            KEY_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"}
        )
        resp.raise_for_status()
        return resp.json()["data"]


async def get_credits() -> dict:
    """Account-level deposit balance (total_credits, total_usage) — distinct
    from get_key_usage()'s per-key usage/limit fields, which stay null until
    a spending cap is configured on the key itself."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            CREDITS_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"}
        )
        resp.raise_for_status()
        return resp.json()["data"]
