from app.db import SessionLocal
from app.models import User


def _seed_user():
    with SessionLocal() as db:
        db.add(User(name="Test User"))
        db.commit()


def test_settings_requires_auth(client):
    assert client.get("/api/settings").status_code == 401
    assert client.patch("/api/settings", json={"default_model": "sonnet"}).status_code == 401


def test_get_settings_defaults_to_auto_with_no_user(authed_client):
    resp = authed_client.get("/api/settings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["default_model"] == "auto"
    keys = [o["key"] for o in body["options"]]
    assert keys == ["auto", "sonnet", "gpt", "cheap", "qwen"]


def test_patch_settings_updates_and_persists(authed_client):
    _seed_user()

    resp = authed_client.patch("/api/settings", json={"default_model": "gpt"})
    assert resp.status_code == 200
    assert resp.json()["default_model"] == "gpt"

    resp = authed_client.get("/api/settings")
    assert resp.json()["default_model"] == "gpt"


def test_patch_settings_rejects_unknown_model(authed_client):
    _seed_user()

    resp = authed_client.patch("/api/settings", json={"default_model": "not-a-real-choice"})

    assert resp.status_code == 400
