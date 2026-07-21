from sqlalchemy.orm import Session

from app.models import Goal, HouseholdMember, User, UserFact

TONE_DESCRIPTIONS = {
    "coach-motivating": (
        "motivating, opinionated, direct — not a generic assistant. "
        "Push back when something looks off (e.g. absurd numbers or claims), "
        "but keep replies concise since they're read on a phone."
    ),
}


def system_prompt(db: Session) -> str:
    user = db.query(User).first()
    if user is None:
        return "You are LifeOS, a personal accountability assistant. Keep replies concise."

    tone = TONE_DESCRIPTIONS.get(user.tone_profile or "", "helpful and concise")
    lines = [
        f"You are LifeOS, {user.name}'s personal AI accountability coach.",
        f"Tone: {tone}",
        f"Address him as {user.name}.",
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

    return " ".join(lines)
