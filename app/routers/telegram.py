import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app import ollama_client, redis_client
from app.config import settings
from app.telegram_client import send_message
from app.tools import TOOLS, make_executor

logger = logging.getLogger("lifeos.telegram")

router = APIRouter()

SYSTEM_PROMPT = (
    "You are LifeOS, a personal assistant. Use get_driving_directions when asked "
    "how long a car trip will take, or for a Google Maps link to an address. Use "
    "get_train_departures when asked about train times between stations (e.g. "
    "Bochnia and Kraków Główny). Only call a tool when the question actually needs "
    "live directions or train data."
)


async def _reply_with_ollama(chat_id: int, text: str) -> None:
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        reply = await ollama_client.chat_with_tools(
            settings.ollama_model, messages, TOOLS, make_executor(chat_id)
        )
    except Exception:
        logger.exception("Ollama call failed")
        reply = "Sorry, the local model didn't respond — check the Ollama connection."
    await send_message(chat_id, reply)


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

    location = message.get("location")
    if chat_id is not None and location:
        background_tasks.add_task(_handle_location, chat_id, location)
        return {"ok": True}

    text = message.get("text", "")
    if chat_id is not None and text:
        background_tasks.add_task(_reply_with_ollama, chat_id, text)

    return {"ok": True}
