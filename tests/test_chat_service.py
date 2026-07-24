from unittest.mock import AsyncMock

from app import chat_service, chat_store, tools
from app.db import SessionLocal
from app.models import InteractionLog, User
from app.ollama_client import TerminalToolResult


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


async def test_run_turn_persists_real_tool_calls_as_audit_trail(monkeypatch):
    """Added after a live incident where the local model described creating
    five calendar events it never actually called create_calendar_event
    for. tool_calls_json must reflect what genuinely ran, not what the reply
    claims — this is what makes that checkable without a manual calendar-API
    lookup next time."""

    async def fake_chat_with_tools(model, messages, tools_list, executor):
        await executor("get_health_summary", {"period": "week"})
        return {"content": "Twoja aktywność...", "prompt_tokens": 10, "completion_tokens": 5}

    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(
        tools.health_client, "get_health_summary", AsyncMock(return_value="steps: 5000")
    )

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "how active was I this week?")

    messages = chat_store.list_all_messages(session_id)
    assistant_msg = next(m for m in messages if m.role == "assistant")
    assert assistant_msg.tool_calls_json == [
        {"name": "get_health_summary", "args": {"period": "week"}}
    ]


async def test_run_turn_persists_no_tool_calls_when_none_were_made(monkeypatch):
    mock_chat = AsyncMock(
        return_value={"content": "just chatting", "prompt_tokens": 1, "completion_tokens": 1}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "hi")

    messages = chat_store.list_all_messages(session_id)
    assistant_msg = next(m for m in messages if m.role == "assistant")
    assert assistant_msg.tool_calls_json is None


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


async def test_run_turn_records_cloud_usage_when_consult_tool_invoked(monkeypatch):
    async def fake_chat_with_tools(model, messages, tools_list, executor):
        result = await executor("consult_advanced_model", {"question": "what should I eat?"})
        reply = result.content if isinstance(result, TerminalToolResult) else result
        return {"content": reply, "prompt_tokens": 5, "completion_tokens": 3}

    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(
        tools.reasoning_client, "consult", AsyncMock(return_value=("cloud advice", 42))
    )

    session_id = _make_session()
    reply = await chat_service.run_turn(session_id, session_id, "web", "advise me")

    assert reply == "cloud advice"
    with SessionLocal() as db:
        logs = db.query(InteractionLog).order_by(InteractionLog.id).all()
    assert logs[1].direction == "out"
    assert logs[1].tokens_cloud == 42
    assert logs[1].redaction_applied == "yes"


async def test_run_turn_persists_cloud_tokens_not_local_tokens_on_terminal_path(monkeypatch):
    """The chat_message.tokens column should reflect the reply's actual
    source — the cloud completion, not the local model's tool-decision
    tokens — since the terminal path means Qwen's own token count doesn't
    correspond to the content that was actually sent to the user."""

    async def fake_chat_with_tools(model, messages, tools_list, executor):
        result = await executor("consult_advanced_model", {"question": "what should I eat?"})
        reply = result.content if isinstance(result, TerminalToolResult) else result
        return {"content": reply, "prompt_tokens": 5, "completion_tokens": 3}

    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(
        tools.reasoning_client, "consult", AsyncMock(return_value=("cloud advice", 42))
    )

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "advise me")

    with SessionLocal() as db:
        from app.models import ChatMessage

        assistant_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
            .one()
        )
    assert assistant_msg.tokens == 42


async def test_run_turn_tags_reply_with_local_model_when_no_cloud_used(monkeypatch):
    mock_chat = AsyncMock(
        return_value={"content": "ok", "prompt_tokens": 1, "completion_tokens": 1}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "hi")

    messages = chat_store.list_all_messages(session_id)
    assistant_msg = next(m for m in messages if m.role == "assistant")
    assert assistant_msg.model == chat_service.settings.ollama_model


async def test_run_turn_tags_reply_with_cloud_model_on_terminal_path(monkeypatch):
    async def fake_chat_with_tools(model, messages, tools_list, executor):
        result = await executor("consult_advanced_model", {"question": "what should I eat?"})
        reply = result.content if isinstance(result, TerminalToolResult) else result
        return {"content": reply, "prompt_tokens": 5, "completion_tokens": 3}

    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(
        tools.reasoning_client, "consult", AsyncMock(return_value=("cloud advice", 42))
    )

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "advise me")

    messages = chat_store.list_all_messages(session_id)
    assistant_msg = next(m for m in messages if m.role == "assistant")
    assert assistant_msg.model == chat_service.settings.openrouter_model


async def test_run_turn_leaves_model_none_on_ollama_exception(monkeypatch):
    mock_chat = AsyncMock(side_effect=ConnectionError("ollama unreachable"))
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "hi")

    messages = chat_store.list_all_messages(session_id)
    assistant_msg = next(m for m in messages if m.role == "assistant")
    assert assistant_msg.model is None


async def test_run_turn_publishes_thinking_local_status_for_web_channel(monkeypatch):
    published = []
    monkeypatch.setattr(
        chat_service.redis_client,
        "publish_status_event",
        AsyncMock(side_effect=lambda sid, status: published.append((sid, status))),
    )
    mock_chat = AsyncMock(
        return_value={"content": "ok", "prompt_tokens": 1, "completion_tokens": 1}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session("web")
    await chat_service.run_turn(session_id, session_id, "web", "hi")

    assert (session_id, "thinking_local") in published


async def test_run_turn_does_not_publish_status_for_telegram_channel(monkeypatch):
    status_mock = AsyncMock()
    monkeypatch.setattr(chat_service.redis_client, "publish_status_event", status_mock)
    mock_chat = AsyncMock(
        return_value={"content": "ok", "prompt_tokens": 1, "completion_tokens": 1}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session("telegram")
    await chat_service.run_turn(session_id, session_id, "telegram", "hi")

    status_mock.assert_not_awaited()


async def test_run_turn_publishes_thinking_cloud_status_around_consult_tool(monkeypatch):
    # chat_service.redis_client and tools.redis_client are the same module
    # object (both are plain `from app import redis_client`) — patch it once.
    published = []
    monkeypatch.setattr(
        chat_service.redis_client,
        "publish_status_event",
        AsyncMock(side_effect=lambda sid, status: published.append((sid, status))),
    )
    monkeypatch.setattr(
        tools.reasoning_client, "consult", AsyncMock(return_value=("cloud advice", 10))
    )

    async def fake_chat_with_tools(model, messages, tools_list, executor):
        result = await executor("consult_advanced_model", {"question": "what should I eat?"})
        reply = result.content if isinstance(result, TerminalToolResult) else result
        return {"content": reply, "prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", fake_chat_with_tools)

    session_id = _make_session("web")
    await chat_service.run_turn(session_id, session_id, "web", "advise me")

    assert (session_id, "thinking_cloud") in published


async def test_run_turn_marks_redaction_not_applied_when_only_local_used(monkeypatch):
    mock_chat = AsyncMock(
        return_value={"content": "ok", "prompt_tokens": 5, "completion_tokens": 3}
    )
    monkeypatch.setattr(chat_service.ollama_client, "chat_with_tools", mock_chat)

    session_id = _make_session()
    await chat_service.run_turn(session_id, session_id, "web", "hi")

    with SessionLocal() as db:
        logs = db.query(InteractionLog).order_by(InteractionLog.id).all()
    assert logs[1].tokens_cloud is None
    assert logs[1].redaction_applied == "n/a (local-only)"


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
