import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Goal, HouseholdMember, User, UserFact

TIMEZONE = "Europe/Warsaw"

TONE_DESCRIPTIONS = {
    "coach-motivating": (
        "motivating, opinionated, direct — not a generic assistant. "
        "Push back when something looks off (e.g. absurd numbers or claims), "
        "but keep replies concise since they're read on a phone."
    ),
}

TOOL_GUIDANCE = (
    "You can call get_driving_directions (destination can be an address or a saved "
    "place name like 'mom' or 'work'), get_train_departures (returns the next several "
    "upcoming departures, default 4, between two Polish train stations — defaults to "
    "the Bochnia <-> Kraków Główny commute if only one station given), "
    "plan_train_commute (use when the user says they're heading to work by train soon "
    "— combines driving time to Bochnia station with the next train to Kraków Główny), "
    "update_saved_place (save or update a named place's address, e.g. when the "
    "user tells you their mom's address), list_calendar_events, create_calendar_event, "
    "update_calendar_event, and delete_calendar_event. For calendar events: resolve "
    "relative dates/times ('Wednesday', 'tomorrow', '7am') into an actual ISO 8601 "
    "datetime yourself using the current date/time given below before calling a tool — "
    "the tools do not parse natural language dates. Calendar events default to the "
    "'primary' calendar; only use 'family' if the user explicitly says family/shared "
    "calendar. To update or delete an event you don't already have the id for from this "
    "conversation, call list_calendar_events first to find it. Take calendar actions "
    "immediately without asking for confirmation first, and always state the exact "
    "resulting date/time in your reply so mistakes are easy to catch. Only call a tool "
    "when the question actually needs live data or a change to be made."
)


def system_prompt(db: Session) -> str:
    user = db.query(User).first()
    if user is None:
        return "You are LifeOS, a personal accountability assistant. Keep replies concise."

    tone = TONE_DESCRIPTIONS.get(user.tone_profile or "", "helpful and concise")
    now = dt.datetime.now(ZoneInfo(TIMEZONE))
    lines = [
        f"You are LifeOS, {user.name}'s personal AI accountability coach.",
        f"Tone: {tone}",
        f"Address him as {user.name}.",
        f"Current date/time: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')}), {TIMEZONE}.",
    ]

    household = db.query(HouseholdMember).all()
    if household:
        household_str = "; ".join(
            f"{m.relation}: {m.name}" + (f" ({m.notes})" if m.notes else "") for m in household
        )
        lines.append(f"Household: {household_str}.")

    goals = db.query(Goal).filter(Goal.status == "active").all()
    if goals:
        goals_str = "; ".join(
            f"{g.title} (target: {g.target_value or g.target_date}, {g.cadence})" for g in goals
        )
        lines.append(f"Active goals: {goals_str}.")

    facts = db.query(UserFact).filter(UserFact.confirmed_bool.is_(True)).all()
    if facts:
        facts_str = "; ".join(f"{f.key}: {f.value}" for f in facts)
        lines.append(f"Known facts: {facts_str}.")

    lines.append(TOOL_GUIDANCE)

    return " ".join(lines)
