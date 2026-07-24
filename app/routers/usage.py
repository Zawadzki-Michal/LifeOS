"""Surfaces real OpenRouter spend to the webapp — the API key itself never
reaches the frontend, only these derived numbers do."""

import asyncio

from fastapi import APIRouter, Depends

from app import openrouter_client
from app.auth import require_auth

router = APIRouter(prefix="/api/usage", dependencies=[Depends(require_auth)])


@router.get("/openrouter")
async def openrouter_usage():
    data, credits = await asyncio.gather(
        openrouter_client.get_key_usage(), openrouter_client.get_credits()
    )
    daily = data.get("usage_daily") or 0
    deposit_total = credits.get("total_credits")
    deposit_used = credits.get("total_usage")
    deposit_remaining = (
        round(deposit_total - deposit_used, 4)
        if deposit_total is not None and deposit_used is not None
        else None
    )
    return {
        "usage_daily": daily,
        "usage_weekly": data.get("usage_weekly"),
        "usage_monthly": data.get("usage_monthly"),
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "projected_monthly": round(daily * 30, 4),
        "deposit_total": deposit_total,
        "deposit_used": deposit_used,
        "deposit_remaining": deposit_remaining,
    }
