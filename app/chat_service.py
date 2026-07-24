"""Shared core for running one chat turn: system prompt + tool-calling model
call + interaction logging. Used by both the Telegram webhook and the web
app's chat API so the two surfaces can't drift apart.
"""

import datetime as dt
import logging

from app import chat_store, ollama_client, openrouter_client, redis_client
from app.config import settings
from app.db import SessionLocal
from app.model_options import DEFAULT_CHOICE_KEY, MODEL_CHOICES
from app.models import InteractionLog, User
from app.prompts import system_prompt
from app.redaction import redact
from app.routing import strip_local_prefix
from app.tools import TOOLS, make_executor

logger = logging.getLogger("lifeos.chat")

FALLBACK_REPLY = "Sorry, I didn't get a usable response that time — try rephrasing?"
ERROR_REPLY = "Sorry, the local model didn't respond — check the Ollama connection."
CLOUD_ERROR_REPLY = "Sorry, the cloud model didn't respond — try again, or prefix with 'Local:'."


def _log_interaction(
    channel: str,
    direction: str,
    tokens: int | None,
    tokens_cloud: int | None = None,
    redaction_applied: str = "n/a (local-only)",
    agent: str = "chat",
) -> None:
    with SessionLocal() as db:
        db.add(
            InteractionLog(
                ts=dt.datetime.now(dt.timezone.utc),
                direction=direction,
                channel=channel,
                agent=agent,
                tokens_local=tokens,
                tokens_cloud=tokens_cloud,
                redaction_applied=redaction_applied,
            )
        )
        db.commit()


def _build_system_prompt(channel: str, terse: bool, include_tools: bool = True) -> str:
    with SessionLocal() as db:
        return system_prompt(db, channel, terse=terse, include_tools=include_tools)


async def _publish_status(session_id: int, status: str) -> None:
    """Best-effort live "what's happening" ping for the webapp UI — a Redis
    outage must never break the actual chat turn over a nice-to-have."""
    try:
        await redis_client.publish_status_event(session_id, status)
    except Exception:
        logger.exception("Failed to publish live status event")


async def _run_remote_turn(session_id: int, channel: str, text: str, model: str | None = None) -> str:
    """Skips the local tool-calling model entirely — everything without a
    'Local:' prefix (or with the header model-picker set to a cloud choice,
    see app/model_options.py) comes here. Still gets the full persona + this
    session's recent history for continuity, same as the local path, just
    redacted before it leaves the box (see app/redaction.py) and with no
    tool access, since only Qwen's path has tools wired up today.

    `model` is the resolved OpenRouter slug to use (None falls back to
    settings.openrouter_model inside openrouter_client.chat) — always
    reflects what was actually used when persisting chat_message.model,
    rather than assuming Sonnet regardless of the real target.
    """
    status_session_id = session_id if channel == "web" else None
    if status_session_id is not None:
        await _publish_status(status_session_id, "thinking_cloud")

    past_turns = chat_store.get_recent_messages(session_id)
    with SessionLocal() as db:
        system = redact(_build_system_prompt(channel, terse=False, include_tools=False), db)
        history = [{"role": m["role"], "content": redact(m["content"], db)} for m in past_turns]
        redacted_text = redact(text, db)

    messages = [{"role": "system", "content": system}] + history + [
        {"role": "user", "content": redacted_text}
    ]

    completion_tokens = None
    reply_model = model or settings.openrouter_model
    try:
        result = await openrouter_client.chat(messages, model=model, source="chat_cloud")
        reply = result["content"].strip()
        completion_tokens = result.get("completion_tokens")
        _log_interaction(
            channel, "in", None, tokens_cloud=result.get("prompt_tokens"),
            redaction_applied="yes", agent="chat_cloud",
        )
        _log_interaction(
            channel, "out", None, tokens_cloud=completion_tokens,
            redaction_applied="yes", agent="chat_cloud",
        )
    except Exception:
        logger.exception("Direct cloud call failed")
        reply = CLOUD_ERROR_REPLY
        reply_model = None
        _log_interaction(channel, "in", None, redaction_applied="yes", agent="chat_cloud")

    if not reply:
        reply = FALLBACK_REPLY

    chat_store.append_message(session_id, "user", text)
    chat_store.append_message(
        session_id, "assistant", reply, tokens=completion_tokens, model=reply_model
    )
    return reply


async def run_turn(
    session_id: int, context_id: int | str, channel: str, text: str, terse: bool = False
) -> str:
    """Run one chat turn and return the reply text.

    `session_id` is the chat_session this turn's history is read from and
    appended to (durable, Postgres-backed). `context_id` is a separate id
    used only for the tool executor's per-conversation ephemeral state (e.g.
    Telegram's shared-location cache) — a Telegram chat_id today, the same
    as `session_id` for the web app once that lands, since it has no
    equivalent device-level state yet.

    A message starting with "Local:" is routed to the local tool-calling
    model below; anything else is resolved against the user's header
    model-picker choice (app/model_options.py, default "auto"): a cloud
    choice skips straight to _run_remote_turn with that model, while
    "Qwen" routes to the local path below even without the prefix.
    """
    is_local, text = strip_local_prefix(text)
    if not is_local:
        with SessionLocal() as db:
            user = db.query(User).first()
        choice_key = (user.default_chat_model if user else None) or DEFAULT_CHOICE_KEY
        choice = MODEL_CHOICES.get(choice_key, MODEL_CHOICES[DEFAULT_CHOICE_KEY])
        if choice["local"]:
            is_local = True
        else:
            return await _run_remote_turn(session_id, channel, text, model=choice["slug"])

    past_turns = chat_store.get_recent_messages(session_id)
    messages = (
        [{"role": "system", "content": _build_system_prompt(channel, terse)}]
        + past_turns
        + [{"role": "user", "content": text}]
    )

    # Live status pings (transcribing/thinking_local/thinking_cloud) are only
    # meaningful to the webapp UI — Telegram has nowhere to show them.
    status_session_id = session_id if channel == "web" else None
    if status_session_id is not None:
        await _publish_status(status_session_id, "thinking_local")

    completion_tokens = None
    usage: dict = {}
    reply_model: str | None = None
    try:
        result = await ollama_client.chat_with_tools(
            settings.ollama_model,
            messages,
            TOOLS,
            make_executor(context_id, usage, status_session_id=status_session_id),
        )
        reply = result["content"].strip()
        # interaction_log always reflects real local Ollama spend for this
        # turn; the persisted chat_message's token count/model instead
        # reflect the cloud completion when that's what the reply actually
        # is (the terminal consult_advanced_model path — see TerminalToolResult).
        completion_tokens = result["completion_tokens"]
        reply_model = settings.openrouter_model if usage.get("cloud_used") else settings.ollama_model
        _log_interaction(channel, "in", result["prompt_tokens"])
        _log_interaction(
            channel,
            "out",
            result["completion_tokens"],
            tokens_cloud=usage.get("cloud_tokens"),
            redaction_applied="yes" if usage.get("cloud_used") else "n/a (local-only)",
        )
        if usage.get("cloud_used"):
            completion_tokens = usage.get("cloud_tokens")
    except Exception:
        logger.exception("Ollama call failed")
        reply = ERROR_REPLY
        _log_interaction(channel, "in", None)

    if not reply:
        logger.warning("Model returned an empty reply for message: %r", text)
        reply = FALLBACK_REPLY

    chat_store.append_message(session_id, "user", text)
    chat_store.append_message(
        session_id,
        "assistant",
        reply,
        tokens=completion_tokens,
        tool_calls=usage.get("tool_calls"),
        model=reply_model,
    )
    return reply
