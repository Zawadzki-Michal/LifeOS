import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app import chat_service, chat_store, redis_client
from app.config import settings
from app.telegram_client import send_message

logger = logging.getLogger("lifeos.telegram")

router = APIRouter()


async def _reply_with_ollama(chat_id: int, text: str) -> None:
    session = chat_store.get_or_create_telegram_session()
    reply = await chat_service.run_turn(session.id, chat_id, "telegram", text)
    try:
        await send_message(chat_id, reply)
    except Exception:
        logger.exception("Failed to send Telegram reply")


async def _handle_reset(chat_id: int) -> None:
    session = chat_store.get_or_create_telegram_session()
    chat_store.clear_session_messages(session.id)
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
