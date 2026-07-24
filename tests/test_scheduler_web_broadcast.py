"""Proactive scheduler messages (morning/evening briefs, bill reminders)
should reach the web app in real time, not just Telegram — see
scheduler._broadcast_to_web and 03-WEBAPP-PLAN.md's stretch goal for this."""

from unittest.mock import AsyncMock

from app import chat_store, scheduler
from app.config import settings


async def test_broadcast_to_web_persists_and_publishes(monkeypatch):
    published = {}

    async def fake_publish(session_id, message):
        published["session_id"] = session_id
        published["message"] = message

    monkeypatch.setattr(scheduler.redis_client, "publish_chat_event", fake_publish)

    await scheduler._broadcast_to_web("Good morning!")

    session = chat_store.get_or_create_scheduler_session()
    messages = chat_store.list_all_messages(session.id)
    assert messages[-1].content == "Good morning!"
    assert messages[-1].model == scheduler.settings.ollama_model
    assert published["session_id"] == session.id
    assert published["message"]["content"] == "Good morning!"
    assert published["message"]["model"] == scheduler.settings.ollama_model


async def test_send_composed_message_mirrors_reply_to_web(monkeypatch):
    monkeypatch.setattr(settings, "telegram_allowed_user_id", 424242)
    monkeypatch.setattr(scheduler, "send_message", AsyncMock())
    monkeypatch.setattr(
        scheduler.ollama_client, "chat", AsyncMock(return_value={"content": "morning brief text"})
    )

    await scheduler._send_composed_message("context", "instruction")

    session = chat_store.get_or_create_scheduler_session()
    messages = chat_store.list_all_messages(session.id)
    assert messages[-1].content == "morning brief text"


async def test_run_daily_checks_mirrors_each_message_to_web(monkeypatch):
    monkeypatch.setattr(settings, "telegram_allowed_user_id", 424242)
    monkeypatch.setattr(scheduler, "send_message", AsyncMock())
    monkeypatch.setattr(scheduler.finance_client, "_post_due_bills", lambda db: (["Mortgage"], []))
    monkeypatch.setattr(scheduler.finance_client, "bills_due_for_reminder", lambda db: [])
    monkeypatch.setattr(scheduler.finance_client, "check_budget_alerts", lambda db: [])
    monkeypatch.setattr(scheduler.health_client, "check_sync_health", AsyncMock(return_value=[]))

    await scheduler.run_daily_checks()

    session = chat_store.get_or_create_scheduler_session()
    messages = chat_store.list_all_messages(session.id)
    assert any(m.content == "Auto-posted recurring bill: Mortgage." for m in messages)


async def test_broadcast_failure_does_not_break_telegram_send(monkeypatch):
    """Telegram delivery must not be held hostage by a webapp-mirroring bug —
    same best-effort philosophy as the rest of the scheduler's error handling."""
    monkeypatch.setattr(settings, "telegram_allowed_user_id", 424242)
    telegram_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "send_message", telegram_mock)
    monkeypatch.setattr(scheduler.finance_client, "_post_due_bills", lambda db: (["Mortgage"], []))
    monkeypatch.setattr(scheduler.finance_client, "bills_due_for_reminder", lambda db: [])
    monkeypatch.setattr(scheduler.finance_client, "check_budget_alerts", lambda db: [])
    monkeypatch.setattr(scheduler.health_client, "check_sync_health", AsyncMock(return_value=[]))

    async def broken_broadcast(text):
        raise RuntimeError("redis is down")

    monkeypatch.setattr(scheduler, "_broadcast_to_web", broken_broadcast)

    await scheduler.run_daily_checks()

    telegram_mock.assert_awaited_once_with(424242, "Auto-posted recurring bill: Mortgage.")
