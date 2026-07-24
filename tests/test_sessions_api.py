from unittest.mock import AsyncMock

from app import chat_store


def test_sessions_require_auth(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 401


def test_auth_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_auth_me_returns_email_when_authed(authed_client):
    resp = authed_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json() == {"email": "test@example.com", "name": None}


def test_auth_me_returns_user_name_when_present(authed_client):
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.add(User(name="Michal"))
        db.commit()

    resp = authed_client.get("/api/auth/me")

    assert resp.status_code == 200
    assert resp.json() == {"email": "test@example.com", "name": "Michal"}


def test_create_and_list_sessions(authed_client):
    resp = authed_client.post("/api/sessions", json={})
    assert resp.status_code == 200
    created = resp.json()
    assert created["channel"] == "web"
    assert created["title"] is None
    assert created["archived"] is False

    resp = authed_client.get("/api/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == created["id"]


def test_rename_session(authed_client):
    created = authed_client.post("/api/sessions", json={}).json()

    resp = authed_client.patch(f"/api/sessions/{created['id']}", json={"title": "New title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"


def test_archive_hides_from_default_list_but_not_from_include_archived(authed_client):
    created = authed_client.post("/api/sessions", json={}).json()

    resp = authed_client.patch(f"/api/sessions/{created['id']}", json={"archived": True})
    assert resp.status_code == 200
    assert resp.json()["archived"] is True

    assert authed_client.get("/api/sessions").json() == []

    all_sessions = authed_client.get("/api/sessions?include_archived=true").json()
    assert len(all_sessions) == 1
    assert all_sessions[0]["archived"] is True


def test_restore_archived_session(authed_client):
    created = authed_client.post("/api/sessions", json={}).json()
    authed_client.patch(f"/api/sessions/{created['id']}", json={"archived": True})

    resp = authed_client.patch(f"/api/sessions/{created['id']}", json={"archived": False})
    assert resp.status_code == 200

    assert len(authed_client.get("/api/sessions").json()) == 1


def test_delete_session_removes_it_permanently(authed_client):
    created = authed_client.post("/api/sessions", json={}).json()

    resp = authed_client.delete(f"/api/sessions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    assert authed_client.get("/api/sessions?include_archived=true").json() == []


def test_web_api_cannot_see_or_touch_telegram_session(authed_client):
    telegram_session = chat_store.get_or_create_telegram_session()

    resp = authed_client.get(f"/api/sessions/{telegram_session.id}/messages")
    assert resp.status_code == 404

    resp = authed_client.patch(f"/api/sessions/{telegram_session.id}", json={"title": "hijacked"})
    assert resp.status_code == 404

    resp = authed_client.delete(f"/api/sessions/{telegram_session.id}")
    assert resp.status_code == 404


def test_send_message_requires_nonempty_text(authed_client):
    created = authed_client.post("/api/sessions", json={}).json()
    resp = authed_client.post(f"/api/sessions/{created['id']}/messages", json={"text": "  "})
    assert resp.status_code == 400


def test_send_message_returns_reply_and_auto_titles_session(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    mock_run_turn = AsyncMock(return_value="hello back")
    monkeypatch.setattr(sessions_router.chat_service, "run_turn", mock_run_turn)

    created = authed_client.post("/api/sessions", json={}).json()
    resp = authed_client.post(
        f"/api/sessions/{created['id']}/messages", json={"text": "first message here"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"reply": "hello back"}

    updated = authed_client.get("/api/sessions").json()[0]
    assert updated["title"] == "first message here"


def test_send_message_to_missing_session_404s(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(
        sessions_router.chat_service, "run_turn", AsyncMock(return_value="unused")
    )
    resp = authed_client.post("/api/sessions/999999/messages", json={"text": "hi"})
    assert resp.status_code == 404


def test_voice_message_transcribes_and_replies(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(
        sessions_router.speech, "transcribe", AsyncMock(return_value="what's my schedule today")
    )
    monkeypatch.setattr(
        sessions_router.chat_service, "run_turn", AsyncMock(return_value="Nothing on today.")
    )
    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", AsyncMock())

    created = authed_client.post("/api/sessions", json={}).json()
    resp = authed_client.post(
        f"/api/sessions/{created['id']}/voice-messages",
        files={"file": ("voice.webm", b"fake-audio-bytes", "audio/webm")},
    )

    assert resp.status_code == 200
    assert resp.json() == {"transcript": "what's my schedule today", "reply": "Nothing on today."}

    # Voice messages auto-title the session too, same as text ones.
    updated = authed_client.get("/api/sessions").json()[0]
    assert updated["title"] == "what's my schedule today"


def test_voice_message_publishes_transcribing_status(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(sessions_router.speech, "transcribe", AsyncMock(return_value="hi"))
    monkeypatch.setattr(sessions_router.chat_service, "run_turn", AsyncMock(return_value="ok"))
    status_mock = AsyncMock()
    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", status_mock)

    created = authed_client.post("/api/sessions", json={}).json()
    authed_client.post(
        f"/api/sessions/{created['id']}/voice-messages",
        files={"file": ("voice.webm", b"fake-audio-bytes", "audio/webm")},
    )

    status_mock.assert_awaited_once_with(created["id"], "transcribing")


def test_voice_message_with_no_discernible_speech_returns_400(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(sessions_router.speech, "transcribe", AsyncMock(return_value=""))
    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", AsyncMock())

    created = authed_client.post("/api/sessions", json={}).json()
    resp = authed_client.post(
        f"/api/sessions/{created['id']}/voice-messages",
        files={"file": ("voice.webm", b"silence", "audio/webm")},
    )
    assert resp.status_code == 400


def test_voice_message_to_missing_session_404s(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(sessions_router.speech, "transcribe", AsyncMock(return_value="hi"))
    resp = authed_client.post(
        "/api/sessions/999999/voice-messages",
        files={"file": ("voice.webm", b"fake-audio-bytes", "audio/webm")},
    )
    assert resp.status_code == 404


def test_image_message_analyzes_and_replies(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(
        sessions_router.reasoning_client,
        "analyze_image",
        AsyncMock(return_value=("8000 kroków dzisiaj", 15)),
    )
    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", AsyncMock())

    created = authed_client.post("/api/sessions", json={}).json()
    resp = authed_client.post(
        f"/api/sessions/{created['id']}/image-messages",
        files={"file": ("screenshot.png", b"fake-png-bytes", "image/png")},
        data={"caption": "ile krokow dzisiaj"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"reply": "8000 kroków dzisiaj"}

    messages = authed_client.get(f"/api/sessions/{created['id']}/messages").json()
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "📷 ile krokow dzisiaj"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "8000 kroków dzisiaj"
    assert messages[1]["model"] == sessions_router.settings.openrouter_vision_model

    # Auto-titles the session, same as text/voice messages.
    updated = authed_client.get("/api/sessions").json()[0]
    assert updated["title"] == "📷 ile krokow dzisiaj"


def test_image_message_without_caption_uses_placeholder_title(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(
        sessions_router.reasoning_client, "analyze_image", AsyncMock(return_value=("ok", 5))
    )
    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", AsyncMock())

    created = authed_client.post("/api/sessions", json={}).json()
    authed_client.post(
        f"/api/sessions/{created['id']}/image-messages",
        files={"file": ("screenshot.png", b"fake-png-bytes", "image/png")},
    )

    messages = authed_client.get(f"/api/sessions/{created['id']}/messages").json()
    assert messages[0]["content"] == "📷 [obraz]"


def test_image_message_publishes_analyzing_status(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(
        sessions_router.reasoning_client, "analyze_image", AsyncMock(return_value=("ok", 5))
    )
    status_mock = AsyncMock()
    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", status_mock)

    created = authed_client.post("/api/sessions", json={}).json()
    authed_client.post(
        f"/api/sessions/{created['id']}/image-messages",
        files={"file": ("screenshot.png", b"fake-png-bytes", "image/png")},
    )

    status_mock.assert_awaited_once_with(created["id"], "analyzing_image")


def test_image_message_rejects_empty_upload(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", AsyncMock())

    created = authed_client.post("/api/sessions", json={}).json()
    resp = authed_client.post(
        f"/api/sessions/{created['id']}/image-messages",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 400


def test_image_message_to_missing_session_404s(authed_client):
    resp = authed_client.post(
        "/api/sessions/999999/image-messages",
        files={"file": ("screenshot.png", b"fake-png-bytes", "image/png")},
    )
    assert resp.status_code == 404


def test_image_message_logs_interaction_with_vision_agent(authed_client, monkeypatch):
    from app.routers import sessions as sessions_router

    monkeypatch.setattr(
        sessions_router.reasoning_client, "analyze_image", AsyncMock(return_value=("ok", 15))
    )
    monkeypatch.setattr(sessions_router.redis_client, "publish_status_event", AsyncMock())

    created = authed_client.post("/api/sessions", json={}).json()
    authed_client.post(
        f"/api/sessions/{created['id']}/image-messages",
        files={"file": ("screenshot.png", b"fake-png-bytes", "image/png")},
    )

    from app.db import SessionLocal
    from app.models import InteractionLog

    with SessionLocal() as db:
        log = db.query(InteractionLog).filter(InteractionLog.agent == "vision").one()
    assert log.tokens_cloud == 15
    assert log.channel == "web"
