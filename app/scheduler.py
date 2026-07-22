"""Proactive daily messages: finance checks, morning motivation, evening
feedback. No external scheduler dependency — plain asyncio loops, one per
scheduled time, each sleeping until its next occurrence in Europe/Warsaw.
Started as background tasks from app.main's lifespan.
"""

import asyncio
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from app import calendar_client, finance_client, health_client, maps_client, ollama_client
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

    messages += await health_client.check_sync_health()

    for msg in messages:
        try:
            await send_message(chat_id, msg)
        except Exception:
            logger.exception("Failed to send proactive finance message")


async def _office_commute_note(target_date: dt.date) -> str | None:
    """If an 'office'-titled event exists on target_date with a specific
    time, computes the actual train needed to arrive on time (using the
    established Bochnia<->Kraków commute) — 'what time do I need to leave'
    isn't something the model reliably works out unprompted from a bare
    event time, so it's computed deterministically here instead."""
    events = await calendar_client.fetch_day_events(target_date, ["primary", "family"])
    for title, _, start_dt in events:
        if start_dt is not None and "office" in title.lower():
            trains = await maps_client.get_train_departures(
                "Bochnia", "Kraków Główny", count=3, arrival_time_iso=start_dt.isoformat()
            )
            return f"Commute options for '{title}' at {start_dt.strftime('%H:%M')}: {trains}"
    return None


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
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    snapshot = await health_client.get_daily_snapshot(yesterday)
    today_events = await calendar_client.list_today_events()
    goal_progress = await health_client.get_workout_goal_progress()
    latest_weight = await health_client.get_latest_weight()
    commute = await _office_commute_note(today)

    parts = [f"Yesterday's activity: {snapshot}." if snapshot else "No Apple Health data synced yet."]
    parts.append(f"Calendar: {today_events}")
    if commute:
        parts.append(commute)
    if goal_progress:
        parts.append(f"Goal progress this week: {goal_progress}.")
    if latest_weight:
        parts.append(f"Latest weight: {latest_weight}.")

    await _send_composed_message(
        " ".join(parts),
        "Write a short (3-4 sentence) motivating good-morning message for today, in "
        "your usual tone. Reference yesterday's activity if there's data (otherwise "
        "just motivate for today without mentioning missing data), give a brief "
        "heads-up on anything on today's calendar, and reference goal progress or "
        "weight only if given above — don't invent numbers. Each calendar item is "
        "already labeled '(upcoming)' or '(already started/passed)' — respect that "
        "label exactly: for anything marked already started/passed, ask whether it "
        "happened rather than reminding him to go do it as if it were still ahead. If "
        "a commute note is given above, list all the train options given so he can "
        "pick which fits his morning — don't just pick one for him, and don't invent "
        "times not given to you.",
    )


async def send_evening_feedback() -> None:
    today = dt.date.today()
    tomorrow_date = today + dt.timedelta(days=1)
    snapshot = await health_client.get_daily_snapshot(today)
    spending = await finance_client.get_spending_summary("today")
    tomorrow = await calendar_client.list_tomorrow_events()
    goal_progress = await health_client.get_workout_goal_progress()
    latest_weight = await health_client.get_latest_weight()
    commute = await _office_commute_note(tomorrow_date)

    nothing_to_report = (
        snapshot is None
        and spending.startswith("No expenses logged")
        and tomorrow == "Nothing on the calendar tomorrow."
    )
    if nothing_to_report:
        return

    activity_line = f"Today's activity so far: {snapshot}." if snapshot else "No Health data synced today."
    parts = [activity_line, f"Spending today: {spending}", f"Calendar: {tomorrow}"]
    if commute:
        parts.append(commute)
    if goal_progress:
        parts.append(f"Goal progress this week: {goal_progress}.")
    if latest_weight:
        parts.append(f"Latest weight: {latest_weight}.")

    await _send_composed_message(
        " ".join(parts),
        "Write a short (3-5 sentence) end-of-day wrap-up in your usual tone. Cover: "
        "what happened today activity-wise, whether any expenses were logged today "
        "(say so plainly if none were — don't just skip it), and a brief heads-up on "
        "anything scheduled tomorrow (e.g. remind him to pack gym clothes or prep for "
        "a study session if relevant to what's listed). If a commute note is given "
        "above, list all the train options given so he can pick which fits his "
        "morning — don't just pick one for him, and don't invent times not given to "
        "you. If goal progress or weight is given above, use the real numbers to make the "
        "nudge specific instead of generic. Do not invent events, expenses, goal "
        "counts, weight, or train times that weren't given to you above.",
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
