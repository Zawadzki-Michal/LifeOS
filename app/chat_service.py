"""Shared core for running one chat turn: system prompt + tool-calling model
call + interaction logging. Used by both the Telegram webhook and the web
app's chat API so the two surfaces can't drift apart.
"""

import datetime as dt
import logging

from app import chat_store, ollama_client
from app.config import settings
from app.db import SessionLocal
from app.models import InteractionLog
from app.prompts import system_prompt
from app.tools import TOOLS, make_executor

logger = logging.getLogger("lifeos.chat")

FALLBACK_REPLY = "Sorry, I didn't get a usable response that time — try rephrasing?"
ERROR_REPLY = "Sorry, the local model didn't respond — check the Ollama connection."


def _log_interaction(channel: str, direction: str, tokens: int | None) -> None:
    with SessionLocal() as db:
        db.add(
            InteractionLog(
                ts=dt.datetime.now(dt.timezone.utc),
                direction=direction,
                channel=channel,
                agent="chat",
                tokens_local=tokens,
                tokens_cloud=None,
                redaction_applied="n/a (local-only)",
            )
        )
        db.commit()


def _build_system_prompt(channel: str) -> str:
    with SessionLocal() as db:
        return system_prompt(db, channel)


async def run_turn(session_id: int, context_id: int | str, channel: str, text: str) -> str:
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
        [{"role": "system", "content": _build_system_prompt(channel)}]
        + past_turns
        + [{"role": "user", "content": text}]
    )

    completion_tokens = None
    try:
        result = await ollama_client.chat_with_tools(
            settings.ollama_model, messages, TOOLS, make_executor(context_id)
        )
        reply = result["content"].strip()
        completion_tokens = result["completion_tokens"]
        _log_interaction(channel, "in", result["prompt_tokens"])
        _log_interaction(channel, "out", result["completion_tokens"])
    except Exception:
        logger.exception("Ollama call failed")
        reply = ERROR_REPLY
        _log_interaction(channel, "in", None)

    if not reply:
        logger.warning("Model returned an empty reply for message: %r", text)
        reply = FALLBACK_REPLY

    chat_store.append_message(session_id, "user", text)
    chat_store.append_message(session_id, "assistant", reply, tokens=completion_tokens)
    return reply
