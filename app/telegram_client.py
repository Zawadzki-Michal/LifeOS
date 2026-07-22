import re

import httpx

from app.config import settings

TELEGRAM_API_BASE = "https://api.telegram.org"

# The model repeatedly ignores the "no markdown" prompt instruction, so
# guarantee clean plain text at the actual send boundary instead of relying
# on compliance — regardless of what it generates, Telegram has no parse_mode
# set and would otherwise show these characters literally.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_UNDERSCORE_BOLD_RE = re.compile(r"__(.+?)__")
_HEADER_RE = re.compile(r"^#{1,6}\s*", flags=re.MULTILINE)


def _strip_markdown(text: str) -> str:
    text = _BOLD_RE.sub(r"\1", text)
    text = _UNDERSCORE_BOLD_RE.sub(r"\1", text)
    text = _HEADER_RE.sub("", text)
    return text


async def send_message(chat_id: int, text: str) -> dict:
    url = f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"chat_id": chat_id, "text": _strip_markdown(text)})
        resp.raise_for_status()
        return resp.json()
