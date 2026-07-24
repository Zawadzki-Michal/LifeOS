from app import chat_store


def test_get_or_create_scheduler_session_is_idempotent():
    first = chat_store.get_or_create_scheduler_session()
    second = chat_store.get_or_create_scheduler_session()

    assert first.id == second.id
    assert first.channel == "web"
    assert first.is_scheduler is True


def test_scheduler_session_is_distinct_from_regular_web_sessions():
    scheduler_session = chat_store.get_or_create_scheduler_session()
    regular_session = chat_store.create_session("web")

    assert scheduler_session.id != regular_session.id
    assert regular_session.is_scheduler is False


def test_append_message_returns_the_created_message():
    session = chat_store.create_session("web")
    message = chat_store.append_message(session.id, "assistant", "hello")

    assert message.id is not None
    assert message.role == "assistant"
    assert message.content == "hello"
    assert message.created_at is not None


def test_append_message_persists_model_attribution():
    session = chat_store.create_session("web")
    message = chat_store.append_message(
        session.id, "assistant", "hello", model="anthropic/claude-sonnet-5"
    )

    assert message.model == "anthropic/claude-sonnet-5"

    stored = chat_store.list_all_messages(session.id)[0]
    assert stored.model == "anthropic/claude-sonnet-5"


def test_append_message_model_defaults_to_none():
    session = chat_store.create_session("web")
    message = chat_store.append_message(session.id, "user", "hi")

    assert message.model is None
