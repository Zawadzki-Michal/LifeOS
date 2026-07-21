import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app import ollama_client
from app.config import settings
from app.telegram_client import send_message

logger = logging.getLogger("lifeos.telegram")

router = APIRouter()


async def _reply_with_ollama(chat_id: int, text: str) -> None:
    try:
        reply = await ollama_client.chat(
            settings.ollama_model,
            [{"role": "user", "content": text}],
        )
    except Exception:
        logger.exception("Ollama call failed")
        reply = "Sorry, the local model didn't respond — check the Ollama connection."
    await send_message(chat_id, reply)


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    sender_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    allowed = settings.telegram_allowed_user_id
    if allowed is None:
        logger.warning(
            "TELEGRAM_ALLOWED_USER_ID not set — accepting message from %s", sender_id
        )
    elif sender_id != allowed:
        logger.info("Ignoring message from unauthorized user %s", sender_id)
        return {"ok": True}

    if chat_id is not None and text:
        background_tasks.add_task(_reply_with_ollama, chat_id, text)

    return {"ok": True}
