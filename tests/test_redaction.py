"""redaction.py is the Redaction Gateway (MASTER_SPEC.md §5.4) — the last
line of defense before household PII reaches OpenRouter. Deterministic
string replacement, not prompt-based, so it must actually catch real names
regardless of case/word-boundary edge cases."""

from app.db import SessionLocal
from app.models import HouseholdMember, User
from app.redaction import redact


def _seed_household():
    with SessionLocal() as db:
        db.add(User(name="Michal"))
        db.add(HouseholdMember(relation="wife", name="Ania"))
        db.add(HouseholdMember(relation="daughter", name="Martina"))
        db.commit()


def test_redacts_household_member_name():
    _seed_household()
    with SessionLocal() as db:
        result = redact("Ania is picking up the kids today.", db)
    assert "Ania" not in result
    assert "[wife]" in result


def test_redacts_user_name():
    _seed_household()
    with SessionLocal() as db:
        result = redact("Michal wants a meal under 600kcal.", db)
    assert "Michal" not in result
    assert "[user]" in result


def test_redaction_is_case_insensitive():
    _seed_household()
    with SessionLocal() as db:
        result = redact("ania and ANIA both said hi.", db)
    assert "ania" not in result.lower()
    assert result.lower().count("[wife]") == 2


def test_does_not_partially_match_substrings():
    _seed_household()
    with SessionLocal() as db:
        result = redact("Aniamaria is a different person entirely.", db)
    assert result == "Aniamaria is a different person entirely."


def test_no_household_data_leaves_text_untouched():
    with SessionLocal() as db:
        result = redact("Plain text with no PII in it.", db)
    assert result == "Plain text with no PII in it."


def test_empty_text_returns_empty():
    with SessionLocal() as db:
        assert redact("", db) == ""
