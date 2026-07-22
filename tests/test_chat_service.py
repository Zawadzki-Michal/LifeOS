from unittest.mock import AsyncMock

from app import chat_service, chat_store
from app.db import SessionLocal
from app.models import InteractionLog, User


def _make_session(channel="web") -> int:
    s = chat_store.create_session(channel)
    return s.id


async def test_run_turn_persists_user_and_assistant_messages(monkeypatch):
    mock_chat = AsyncMock(
        return_value={"content": "Hi there!", "prompt_tokens": 100, "completion_tokens": 20}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    reply = await chat_service.run_turn(session_id, session_id, "web", "hello")

    assert reply == "Hi there!"
    messages = chat_store.get_recent_messages(session_id)
    assert messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]


async def test_run_turn_logs_interaction_with_channel(monkeypatch):
    mock_chat = AsyncMock(
        return_value={"content": "ok", "prompt_tokens": 50, "completion_tokens": 10}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "telegram", "hi")

    with SessionLocal() as db:
        logs = db.query(InteractionLog).order_by(InteractionLog.id).all()
    assert [log.direction for log in logs] == ["in", "out"]
    assert all(log.channel == "telegram" for log in logs)
    assert logs[0].tokens_local == 50
    assert logs[1].tokens_local == 10


async def test_run_turn_falls_back_on_empty_reply(monkeypatch):
    mock_chat = AsyncMock(return_value={"content": "  ", "prompt_tokens": 5, "completion_tokens": 0})
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    reply = await chat_service.run_turn(session_id, session_id, "web", "hello")

    assert reply == chat_service.FALLBACK_REPLY
    messages = chat_store.get_recent_messages(session_id)
    assert messages[-1] == {"role": "assistant", "content": chat_service.FALLBACK_REPLY}


async def test_run_turn_falls_back_on_ollama_exception(monkeypatch):
    mock_chat = AsyncMock(side_effect=ConnectionError("ollama unreachable"))
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    reply = await chat_service.run_turn(session_id, session_id, "web", "hello")

    assert reply == chat_service.ERROR_REPLY

    with SessionLocal() as db:
        logs = db.query(InteractionLog).all()
    # Only the "in" side is logged when the call itself blows up.
    assert len(logs) == 1
    assert logs[0].direction == "in"
    assert logs[0].tokens_local is None


async def test_run_turn_feeds_prior_history_back_into_next_call(monkeypatch):
    mock_chat = AsyncMock(
        return_value={"content": "first reply", "prompt_tokens": 1, "completion_tokens": 1}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "first message")

    mock_chat.return_value = {"content": "second reply", "prompt_tokens": 1, "completion_tokens": 1}
    await chat_service.run_turn(session_id, session_id, "web", "second message")

    sent_messages = mock_chat.await_args.args[1]  # (model, messages, tools, executor)
    contents = [m["content"] for m in sent_messages]
    assert "first message" in contents
    assert "first reply" in contents
    assert "second message" in contents


async def test_run_turn_uses_channel_aware_system_prompt(monkeypatch):
    # system_prompt() only reaches the channel-aware formatting branch once a
    # User row exists — with none, it short-circuits to a generic fallback.
    with SessionLocal() as db:
        db.add(User(name="Test User"))
        db.commit()

    captured = {}

    async def fake_chat_with_tools(model, messages, tools, executor):
        captured["system"] = messages[0]["content"]
        return {"content": "ok", "prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", fake_chat_with_tools)

    web_session = _make_session("web")
    await chat_service.run_turn(web_session, web_session, "web", "hi")
    assert "renders Markdown" in captured["system"]

    telegram_session = _make_session("telegram")
    await chat_service.run_turn(telegram_session, telegram_session, "telegram", "hi")
    assert "plain text only" in captured["system"]
