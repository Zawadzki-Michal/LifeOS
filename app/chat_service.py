"""Shared core for running one chat turn: system prompt + tool-calling model
call + interaction logging. Used by both the Telegram webhook and the web
app's chat API so the two surfaces can't drift apart.
"""

import datetime as dt
import logging

from app import chat_store, ollama_client, redis_client
from app.config import settings
from app.db import SessionLocal
from app.models import InteractionLog
from app.prompts import system_prompt
from app.tools import TOOLS, make_executor

logger = logging.getLogger("lifeos.chat")

FALLBACK_REPLY = "Sorry, I didn't get a usable response that time — try rephrasing?"
ERROR_REPLY = "Sorry, the local model didn't respond — check the Ollama connection."


def _log_interaction(
    channel: str,
    direction: str,
    tokens: int | None,
    tokens_cloud: int | None = None,
    redaction_applied: str = "n/a (local-only)",
) -> None:
    with SessionLocal() as db:
        db.add(
            InteractionLog(
                ts=dt.datetime.now(dt.timezone.utc),
                direction=direction,
                channel=channel,
                agent="chat",
                tokens_local=tokens,
                tokens_cloud=tokens_cloud,
                redaction_applied=redaction_applied,
            )
        )
        db.commit()


def _build_system_prompt(channel: str, terse: bool) -> str:
    with SessionLocal() as db:
        return system_prompt(db, channel, terse=terse)


async def _publish_status(session_id: int, status: str) -> None:
    """Best-effort live "what's happening" ping for the webapp UI — a Redis
    outage must never break the actual chat turn over a nice-to-have."""
    try:
        await redis_client.publish_status_event(session_id, status)
    except Exception:
        logger.exception("Failed to publish live status event")


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
    """
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
