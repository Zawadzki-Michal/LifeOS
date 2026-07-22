"""Verifies the actual deploy-time operation — `alembic upgrade head` — runs
cleanly against a brand-new database. The rest of the suite uses
Base.metadata.create_all for speed, which only checks that the SQLAlchemy
models are internally consistent, not that the migration chain itself is
valid and applies without conflicts.
"""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.config import settings

MIGRATIONS_DB_NAME = "lifeos_test_migrations"


def test_alembic_upgrade_head_runs_cleanly_on_a_fresh_database(monkeypatch):
    base_url = os.environ["DATABASE_URL"].rsplit("/", 1)[0]
    migrations_url = f"{base_url}/{MIGRATIONS_DB_NAME}"

    admin_engine = create_engine(base_url + "/postgres", isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATIONS_DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{MIGRATIONS_DB_NAME}"'))
    admin_engine.dispose()

    engine = create_engine(migrations_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    engine.dispose()

    try:
        # alembic/env.py reads settings.database_url directly, so the Config
        # object's own sqlalchemy.url isn't enough — the singleton itself
        # needs to point at the throwaway database for this call.
        monkeypatch.setattr(settings, "database_url", migrations_url)
        config = Config("alembic.ini")
        command.upgrade(config, "head")

        inspect_engine = create_engine(migrations_url)
        tables = inspect(inspect_engine).get_table_names()
        inspect_engine.dispose()
        for expected in ("user", "chat_session", "chat_message", "alembic_version"):
            assert expected in tables
    finally:
        admin_engine = create_engine(base_url + "/postgres", isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATIONS_DB_NAME}"'))
        admin_engine.dispose()
