import httpx

from app.config import settings

TELEGRAM_API_BASE = "https://api.telegram.org"


async def send_message(chat_id: int, text: str) -> dict:
    url = f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"chat_id": chat_id, "text": text})
        resp.raise_for_status()
        return resp.json()
