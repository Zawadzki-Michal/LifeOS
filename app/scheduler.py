"""Proactive daily messages: finance checks, morning motivation, evening
feedback. No external scheduler dependency — plain asyncio loops, one per
scheduled time, each sleeping until its next occurrence in Europe/Warsaw.
Started as background tasks from app.main's lifespan.
"""

import asyncio
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from app import finance_client, health_client, ollama_client
from app.config import settings
from app.db import SessionLocal
from app.prompts import system_prompt
from app.telegram_client import send_message

logger = logging.getLogger("lifeos.scheduler")

TZ = ZoneInfo("Europe/Warsaw")

FINANCE_CHECK_TIME = (8, 0)
MORNING_MOTIVATION_TIME = (7, 0)
EVENING_FEEDBACK_TIME = (21, 0)


async def run_daily_checks() -> None:
    chat_id = settings.telegram_allowed_user_id
    if chat_id is None:
        logger.warning("No TELEGRAM_ALLOWED_USER_ID set — skipping daily finance checks.")
        return

    messages: list[str] = []
    with SessionLocal() as db:
        posted, awaiting = finance_client._post_due_bills(db)
        messages += [f"Auto-posted recurring bill: {name}." for name in posted]
        messages += [
            f"'{name}' is due and has a variable amount — tell me the actual amount "
            f"and I'll log it."
            for name in awaiting
        ]

        for bill in finance_client.bills_due_for_reminder(db):
            messages.append(
                f"Reminder: '{bill.name}' ({float(bill.amount_pln):.2f} PLN) due "
                f"{bill.next_due.isoformat()}."
            )

        messages += finance_client.check_budget_alerts(db)

    for msg in messages:
        try:
            await send_message(chat_id, msg)
        except Exception:
            logger.exception("Failed to send proactive finance message")


async def _send_composed_message(context: str, instruction: str) -> None:
    chat_id = settings.telegram_allowed_user_id
    if chat_id is None:
        return

    with SessionLocal() as db:
        sys_prompt = system_prompt(db)

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"{context} {instruction} Do not call any tools — just reply with the message."},
    ]
    result = await ollama_client.chat(settings.ollama_model, messages)
    await send_message(chat_id, result["content"])


async def send_morning_motivation() -> None:
    yesterday = dt.date.today() - dt.timedelta(days=1)
    snapshot = await health_client.get_daily_snapshot(yesterday)
    context = f"Yesterday's activity: {snapshot}." if snapshot else "No Apple Health data synced yet."
    await _send_composed_message(
        context,
        "Write a short (2-3 sentence) motivating good-morning message for today, in "
        "your usual tone. Reference yesterday's activity if there's data, otherwise "
        "just motivate for today without mentioning missing data.",
    )


async def send_evening_feedback() -> None:
    today = dt.date.today()
    snapshot = await health_client.get_daily_snapshot(today)
    if snapshot is None:
        return
    await _send_composed_message(
        f"Today's activity so far (as of the last Health sync): {snapshot}.",
        "Write a short (2-3 sentence) end-of-day feedback message in your usual tone "
        "— acknowledge what got done today, and nudge on anything short of an active "
        "goal's target if relevant.",
    )


def _seconds_until(hour: int, minute: int) -> float:
    now = dt.datetime.now(TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


async def _repeat_daily(hour: int, minute: int, callback) -> None:
    while True:
        await asyncio.sleep(_seconds_until(hour, minute))
        try:
            await callback()
        except Exception:
            logger.exception("Scheduled task %s at %02d:%02d failed", callback.__name__, hour, minute)


def start_background_tasks() -> list[asyncio.Task]:
    schedule = [
        (*MORNING_MOTIVATION_TIME, send_morning_motivation),
        (*FINANCE_CHECK_TIME, run_daily_checks),
        (*EVENING_FEEDBACK_TIME, send_evening_feedback),
    ]
    return [asyncio.create_task(_repeat_daily(hour, minute, cb)) for hour, minute, cb in schedule]
