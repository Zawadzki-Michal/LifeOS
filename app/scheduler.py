"""Daily proactive checks: bill auto-posting, due reminders, and budget alerts.

No external scheduler dependency — a single asyncio loop sleeps until the
next 08:00 Europe/Warsaw, runs the checks, then sleeps again. Started as a
background task from app.main's lifespan.
"""

import asyncio
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from app import finance_client
from app.config import settings
from app.db import SessionLocal
from app.telegram_client import send_message

logger = logging.getLogger("lifeos.scheduler")

TZ = ZoneInfo("Europe/Warsaw")
DAILY_CHECK_HOUR = 8


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


def _seconds_until_next_run() -> float:
    now = dt.datetime.now(TZ)
    target = now.replace(hour=DAILY_CHECK_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


async def daily_loop() -> None:
    while True:
        await asyncio.sleep(_seconds_until_next_run())
        try:
            await run_daily_checks()
        except Exception:
            logger.exception("Daily finance check failed")
