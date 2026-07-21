import logging

from fastapi import APIRouter, Request

from app.config import settings
from app.telegram_client import send_message

logger = logging.getLogger("lifeos.telegram")

router = APIRouter()


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
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

    if chat_id is not None:
        await send_message(chat_id, f"hi Michał — echo: {text}")

    return {"ok": True}
