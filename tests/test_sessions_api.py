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
    assert resp.json() == {"email": "test@example.com"}


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
