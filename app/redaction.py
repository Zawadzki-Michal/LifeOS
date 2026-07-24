"""Minimal Redaction Gateway (MASTER_SPEC.md §5.4): strips household PII from
any text before it leaves the box to a cloud model (OpenRouter). Deterministic
string replacement, not prompt-based — same reasoning as the Markdown-stripping
fix in telegram_client.py: anything that must always hold should be enforced
in code, not left to model compliance.
"""

import re

from sqlalchemy.orm import Session

from app.models import HouseholdMember, User


def _placeholder(relation: str) -> str:
    return f"[{relation.strip().lower()}]"


def redact(text: str, db: Session) -> str:
    if not text:
        return text

    replacements: dict[str, str] = {}

    user = db.query(User).first()
    if user and user.name:
        replacements[user.name] = "[user]"

    for member in db.query(HouseholdMember).all():
        if member.name:
            replacements[member.name] = _placeholder(member.relation)

    result = text
    for name, placeholder in sorted(replacements.items(), key=lambda kv: -len(kv[0])):
        result = re.sub(rf"\b{re.escape(name)}\b", placeholder, result, flags=re.IGNORECASE)
    return result
