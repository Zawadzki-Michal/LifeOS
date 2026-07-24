"""openrouter_client.get_key_usage backs the webapp's usage dashboard
(app/routers/usage.py) — respx mocks OpenRouter's /api/v1/key endpoint."""

import httpx
import respx

from app import openrouter_client
from app.openrouter_client import CREDITS_URL, KEY_URL


@respx.mock
async def test_get_key_usage_returns_the_data_payload():
    respx.get(KEY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "usage": 1.23,
                    "usage_daily": 0.05,
                    "usage_weekly": 0.3,
                    "usage_monthly": 1.23,
                    "limit": None,
                    "limit_remaining": None,
                }
            },
        )
    )

    result = await openrouter_client.get_key_usage()

    assert result["usage_daily"] == 0.05
    assert result["usage_monthly"] == 1.23
    assert result["limit"] is None


@respx.mock
async def test_get_key_usage_sends_bearer_auth():
    route = respx.get(KEY_URL).mock(
        return_value=httpx.Response(200, json={"data": {"usage_daily": 0}})
    )

    await openrouter_client.get_key_usage()

    assert route.calls.last.request.headers["Authorization"].startswith("Bearer ")


@respx.mock
async def test_get_credits_returns_the_data_payload():
    respx.get(CREDITS_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"total_credits": 10, "total_usage": 0.030419}}
        )
    )

    result = await openrouter_client.get_credits()

    assert result["total_credits"] == 10
    assert result["total_usage"] == 0.030419


@respx.mock
async def test_get_credits_sends_bearer_auth():
    route = respx.get(CREDITS_URL).mock(
        return_value=httpx.Response(200, json={"data": {"total_credits": 0, "total_usage": 0}})
    )

    await openrouter_client.get_credits()

    assert route.calls.last.request.headers["Authorization"].startswith("Bearer ")
