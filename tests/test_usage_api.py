from unittest.mock import AsyncMock


def test_usage_requires_auth(client):
    resp = client.get("/api/usage/openrouter")
    assert resp.status_code == 401


def test_usage_returns_real_and_projected_spend(authed_client, monkeypatch):
    from app.routers import usage as usage_router

    monkeypatch.setattr(
        usage_router.openrouter_client,
        "get_key_usage",
        AsyncMock(
            return_value={
                "usage_daily": 0.05,
                "usage_weekly": 0.3,
                "usage_monthly": 1.5,
                "limit": None,
                "limit_remaining": None,
            }
        ),
    )
    monkeypatch.setattr(
        usage_router.openrouter_client,
        "get_credits",
        AsyncMock(return_value={"total_credits": 10, "total_usage": 1.5}),
    )

    resp = authed_client.get("/api/usage/openrouter")

    assert resp.status_code == 200
    body = resp.json()
    assert body["usage_daily"] == 0.05
    assert body["usage_monthly"] == 1.5
    assert body["projected_monthly"] == 1.5  # 0.05 * 30
    assert body["deposit_total"] == 10
    assert body["deposit_used"] == 1.5
    assert body["deposit_remaining"] == 8.5


def test_usage_handles_missing_daily_usage_gracefully(authed_client, monkeypatch):
    from app.routers import usage as usage_router

    monkeypatch.setattr(
        usage_router.openrouter_client,
        "get_key_usage",
        AsyncMock(return_value={"usage_monthly": 0}),
    )
    monkeypatch.setattr(
        usage_router.openrouter_client,
        "get_credits",
        AsyncMock(return_value={"total_credits": None, "total_usage": None}),
    )

    resp = authed_client.get("/api/usage/openrouter")

    assert resp.status_code == 200
    body = resp.json()
    assert body["projected_monthly"] == 0
    assert body["deposit_remaining"] is None
