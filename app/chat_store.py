"""Durable chat history backed by Postgres (chat_session/chat_message),
replacing the old Redis-based history.py as the source of truth. Redis stays
in use for ephemeral state only (e.g. the shared-location cache).
"""

import datetime as dt

from app.db import SessionLocal
from app.models import ChatMessage, ChatSession

MAX_TURNS = 10


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def get_or_create_telegram_session() -> ChatSession:
    """Telegram is locked to a single allowed user (TELEGRAM_ALLOWED_USER_ID),
    so there's exactly one telegram-channel session for the whole deployment.
    """
    with SessionLocal() as db:
        session = db.query(ChatSession).filter(ChatSession.channel == "telegram").first()
        if session is None:
            now = _now()
            session = ChatSession(
                channel="telegram",
                title="Telegram",
                created_at=now,
                updated_at=now,
                archived=False,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        return session


def get_or_create_scheduler_session() -> ChatSession:
    """One persistent web-channel session that proactive scheduler messages
    (morning/evening briefs, bill reminders) are mirrored into, so they also
    show up in the web app in real time — not just Telegram."""
    with SessionLocal() as db:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.channel == "web", ChatSession.is_scheduler.is_(True))
            .first()
        )
        if session is None:
            now = _now()
            session = ChatSession(
                channel="web",
                title="Daily Briefings",
                created_at=now,
                updated_at=now,
                archived=False,
                is_scheduler=True,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        return session


def get_recent_messages(session_id: int, max_turns: int = MAX_TURNS) -> list[dict]:
    with SessionLocal() as db:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.desc())
            .limit(max_turns * 2)
            .all()
        )
    rows.reverse()
    return [{"role": row.role, "content": row.content} for row in rows]


def append_message(
    session_id: int,
    role: str,
    content: str,
    tokens: int | None = None,
    tool_calls: list[dict] | None = None,
    model: str | None = None,
) -> ChatMessage:
    """`tool_calls`, if given, is a real audit trail of what actually ran
    this turn (name + args per tool) — not what the reply claims happened.
    Added after a live incident where the local model confidently described
    creating five calendar events it never actually called the tool for.
    `model`, for assistant replies, is which model actually produced the
    content (e.g. 'qwen3.6:35b-a3b', 'anthropic/claude-sonnet-5',
    'google/gemini-2.5-flash') — surfaced in the webapp so it's visible at a
    glance whether a reply came from the local or cloud model."""
    with SessionLocal() as db:
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            tokens=tokens,
            tool_calls_json=tool_calls,
            model=model,
            created_at=_now(),
        )
        db.add(message)
        db.query(ChatSession).filter(ChatSession.id == session_id).update(
            {"updated_at": _now()}
        )
        db.commit()
        db.refresh(message)
        return message


def clear_session_messages(session_id: int) -> None:
    with SessionLocal() as db:
        db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
        db.commit()


def list_sessions(channel: str, include_archived: bool = False) -> list[ChatSession]:
    with SessionLocal() as db:
        query = db.query(ChatSession).filter(ChatSession.channel == channel)
        if not include_archived:
            query = query.filter(ChatSession.archived.is_(False))
        return query.order_by(ChatSession.updated_at.desc()).all()


def create_session(channel: str, title: str | None = None) -> ChatSession:
    with SessionLocal() as db:
        now = _now()
        session = ChatSession(
            channel=channel, title=title, created_at=now, updated_at=now, archived=False
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session


def get_session(session_id: int, channel: str | None = None) -> ChatSession | None:
    with SessionLocal() as db:
        query = db.query(ChatSession).filter(ChatSession.id == session_id)
        if channel is not None:
            query = query.filter(ChatSession.channel == channel)
        return query.first()


def update_session(
    session_id: int, title: str | None = None, archived: bool | None = None
) -> ChatSession | None:
    with SessionLocal() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session is None:
            return None
        if title is not None:
            session.title = title
        if archived is not None:
            session.archived = archived
        session.updated_at = _now()
        db.commit()
        db.refresh(session)
        return session


def delete_session(session_id: int) -> bool:
    with SessionLocal() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session is None:
            return False
        db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
        db.delete(session)
        db.commit()
        return True


def list_all_messages(session_id: int) -> list[ChatMessage]:
    with SessionLocal() as db:
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
