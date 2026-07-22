import datetime as dt
import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app import history, ollama_client, redis_client
from app.config import settings
from app.db import SessionLocal
from app.models import InteractionLog
from app.prompts import system_prompt
from app.telegram_client import send_message
from app.tools import TOOLS, make_executor

logger = logging.getLogger("lifeos.telegram")

router = APIRouter()


def _log_interaction(direction: str, tokens: int | None) -> None:
    with SessionLocal() as db:
        db.add(
            InteractionLog(
                ts=dt.datetime.now(dt.timezone.utc),
                direction=direction,
                channel="telegram",
                agent="chat",
                tokens_local=tokens,
                tokens_cloud=None,
                redaction_applied="n/a (local-only)",
            )
        )
        db.commit()


def _build_system_prompt() -> str:
    with SessionLocal() as db:
        return system_prompt(db)


async def _reply_with_ollama(chat_id: int, text: str) -> None:
    past_turns = await history.get_history(chat_id)
    messages = (
        [{"role": "system", "content": _build_system_prompt()}]
        + past_turns
        + [{"role": "user", "content": text}]
    )

    try:
        result = await ollama_client.chat_with_tools(
            settings.ollama_model, messages, TOOLS, make_executor(chat_id)
        )
        reply = result["content"].strip()
        _log_interaction("in", result["prompt_tokens"])
        _log_interaction("out", result["completion_tokens"])
    except Exception:
        logger.exception("Ollama call failed")
        reply = "Sorry, the local model didn't respond — check the Ollama connection."
        _log_interaction("in", None)

    if not reply:
        logger.warning("Model returned an empty reply for message: %r", text)
        reply = "Sorry, I didn't get a usable response that time — try rephrasing?"

    await history.append_history(chat_id, text, reply)
    try:
        await send_message(chat_id, reply)
    except Exception:
        logger.exception("Failed to send Telegram reply")


async def _handle_reset(chat_id: int) -> None:
    await history.clear_history(chat_id)
    await send_message(chat_id, "Conversation reset.")


async def _handle_location(chat_id: int, location: dict) -> None:
    await redis_client.set_location(chat_id, location["latitude"], location["longitude"])
    await send_message(
        chat_id, "Got your location — I'll use it for directions until you share a new one."
    )


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    sender_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")

    allowed = settings.telegram_allowed_user_id
    if allowed is None:
        logger.warning(
            "TELEGRAM_ALLOWED_USER_ID not set — accepting message from %s", sender_id
        )
    elif sender_id != allowed:
        logger.info("Ignoring message from unauthorized user %s", sender_id)
        return {"ok": True}

    if chat_id is None:
        return {"ok": True}

    location = message.get("location")
    if location:
        background_tasks.add_task(_handle_location, chat_id, location)
        return {"ok": True}

    text = message.get("text", "")
    if not text:
        return {"ok": True}

    if text.strip() == "/reset":
        background_tasks.add_task(_handle_reset, chat_id)
    else:
        background_tasks.add_task(_reply_with_ollama, chat_id, text)

    return {"ok": True}
