"""Test config. Points the app at a dedicated lifeos_test Postgres database
(never the real dev DB) — env vars here MUST be set before any `app.*`
module is imported anywhere, since app.db builds its engine at import time.
"""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://lifeos:changeme@postgres:5432/lifeos_test",
)
os.environ.setdefault("REDIS_URL", "redis://redis:6379/1")
os.environ.setdefault("TELEGRAM_ALLOWED_USER_ID", "424242")
os.environ.setdefault("WEBAPP_SECRET_KEY", "test-secret-not-for-real-use")
os.environ.setdefault("WEBAPP_ALLOWED_EMAILS", "test@example.com")
# Fake but truthy — these just need to pass the "is it configured" guard in
# maps_client/calendar_client so tests reach the (mocked) HTTP calls instead
# of short-circuiting to "not connected yet".
os.environ.setdefault("GOOGLE_MAPS_API_KEY", "test-maps-key")
os.environ.setdefault("GOOGLE_CALENDAR_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CALENDAR_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_CALENDAR_REFRESH_TOKEN", "test-refresh-token")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import SESSION_COOKIE, create_session_token
from app.db import Base, engine
from app.routers import auth as auth_router
from app.routers import sessions as sessions_router
from app.routers import usage as usage_router


def _ensure_test_database() -> None:
    test_url = os.environ["DATABASE_URL"]
    base_url, db_name = test_url.rsplit("/", 1)
    admin_engine = create_engine(base_url + "/postgres", isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    _ensure_test_database()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
async def _clean_redis():
    # redis_client caches its async client at module level, bound to
    # whichever event loop was running when it was first created. Since
    # pytest-asyncio gives each test function its own event loop, a client
    # created in an earlier test breaks ("attached to a different loop") if
    # reused here — force a fresh one per test instead.
    from app import redis_client

    redis_client._client = None
    yield
    client = redis_client._client
    if client is not None:
        await client.flushdb()
        await client.aclose()
        redis_client._client = None


@pytest.fixture()
def api_app() -> FastAPI:
    """Minimal app with just the routers under test — no lifespan (no seed
    data, no scheduler background tasks), so API tests stay fast and
    self-contained."""
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(sessions_router.router)
    app.include_router(usage_router.router)
    return app


@pytest.fixture()
def client(api_app: FastAPI) -> TestClient:
    return TestClient(api_app)


@pytest.fixture()
def authed_client(client: TestClient) -> TestClient:
    token = create_session_token("test@example.com")
    client.cookies.set(SESSION_COOKIE, token)
    return client
