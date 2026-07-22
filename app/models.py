"""SQLAlchemy models for the V1 schema (MASTER_SPEC.md section 7).

Schema only — no business logic. All timestamps are timestamptz, all money
is numeric(12,2) PLN, all durations are minutes (int).
"""

import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# --- 7.1 Identity & Config ---


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tz: Mapped[str] = mapped_column(String(64), default="Europe/Warsaw")
    locale: Mapped[str] = mapped_column(String(16), default="en")
    quiet_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    tone_profile: Mapped[str | None] = mapped_column(String(64))


class HouseholdMember(Base):
    __tablename__ = "household_member"

    id: Mapped[int] = mapped_column(primary_key=True)
    relation: Mapped[str] = mapped_column(String(32))  # PII context, not the value itself
    name: Mapped[str] = mapped_column(String(120))  # PII
    dob: Mapped[dt.date | None] = mapped_column(Date)  # PII
    notes: Mapped[str | None] = mapped_column(Text)  # PII


# --- 7.2 Goals ---


class Goal(Base):
    __tablename__ = "goal"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # deadline|trajectory|frequency
    title: Mapped[str] = mapped_column(String(200))
    target_value: Mapped[str | None] = mapped_column(String(200))
    target_date: Mapped[dt.date | None] = mapped_column(Date)
    cadence: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="active")


class GoalProgress(Base):
    __tablename__ = "goal_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goal.id"))
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)


class GoalCheckinPolicy(Base):
    __tablename__ = "goal_checkin_policy"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goal.id"))
    rule_json: Mapped[dict] = mapped_column(JSON)


# --- 7.3 Calendar ---


class CalendarSource(Base):
    __tablename__ = "calendar_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="google")
    account_label: Mapped[str] = mapped_column(String(32))  # personal|family
    oauth_ref: Mapped[str | None] = mapped_column(String(200))


class CalendarEvent(Base):
    __tablename__ = "calendar_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("calendar_source.id"))
    external_id: Mapped[str | None] = mapped_column(String(200))
    start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    attendees: Mapped[dict | None] = mapped_column(JSON)
    visibility: Mapped[str] = mapped_column(String(16), default="self")  # self|family|shared


class TravelPlan(Base):
    __tablename__ = "travel_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("calendar_event.id"))
    mode: Mapped[str] = mapped_column(String(16))  # train|car
    depart_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    arrive_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


# --- 7.4 Tasks & Reminders ---


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    priority: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="open")
    source: Mapped[str] = mapped_column(String(16), default="user")  # user|system
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goal.id"))


class Reminder(Base):
    __tablename__ = "reminder"

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(16))  # task|bill|event
    remind_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String(16), default="telegram")


# --- 7.5 Finance ---


class ExpenseCategory(Base):
    __tablename__ = "expense_category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    monthly_budget: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))
    # Last budget-threshold alert sent, as "YYYY-MM:pct" (e.g. "2026-07:100") —
    # dedupes proactive alerts so each threshold only fires once per month.
    last_budget_alert: Mapped[str | None] = mapped_column(String(16))


class Expense(Base):
    __tablename__ = "expense"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    amount_pln: Mapped[Numeric] = mapped_column(Numeric(12, 2))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_category.id"))
    merchant: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)


class Bill(Base):
    __tablename__ = "bill"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    amount_pln: Mapped[Numeric] = mapped_column(Numeric(12, 2))
    due_day: Mapped[int] = mapped_column(Integer)
    recurrence: Mapped[str] = mapped_column(String(16), default="monthly")  # monthly|yearly
    next_due: Mapped[dt.date] = mapped_column(Date)
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=1)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_category.id"))
    # False for bills whose amount varies each cycle (e.g. utilities) — these
    # aren't auto-posted, they wait for a confirmed actual amount instead.
    amount_is_fixed: Mapped[bool] = mapped_column(Boolean, default=True)


class SavingsBucket(Base):
    __tablename__ = "savings_bucket"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Numeric] = mapped_column(Numeric(12, 2))
    target_date: Mapped[dt.date | None] = mapped_column(Date)
    current_amount: Mapped[Numeric] = mapped_column(Numeric(12, 2), default=0)


# --- 7.6 Fitness ---


class WorkoutTemplate(Base):
    __tablename__ = "workout_template"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    exercises_json: Mapped[dict] = mapped_column(JSON)


class WorkoutSession(Base):
    __tablename__ = "workout_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("workout_template.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    rpe: Mapped[Numeric | None] = mapped_column(Numeric(3, 1))
    session_type: Mapped[str] = mapped_column(String(16))  # gym|squash


class SetLog(Base):
    __tablename__ = "set_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("workout_session.id"))
    exercise: Mapped[str] = mapped_column(String(120))
    set_num: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))
    reps: Mapped[int | None] = mapped_column(Integer)
    rir: Mapped[int | None] = mapped_column(Integer)


class ProgressionRule(Base):
    __tablename__ = "progression_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise: Mapped[str] = mapped_column(String(120), unique=True)
    rule_json: Mapped[dict] = mapped_column(JSON)


# --- 7.7 Health ---


class MetricDaily(Base):
    __tablename__ = "metric_daily"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    weight_kg: Mapped[Numeric | None] = mapped_column(Numeric(5, 2))
    resting_hr: Mapped[int | None] = mapped_column(Integer)
    sleep_hours: Mapped[Numeric | None] = mapped_column(Numeric(4, 2))
    hrv: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[int | None] = mapped_column(Integer)
    # Populated by Apple Health sync (app/health_client.py), not in original spec.
    active_kcal: Mapped[Numeric | None] = mapped_column(Numeric(7, 2))
    resting_kcal: Mapped[Numeric | None] = mapped_column(Numeric(7, 2))
    avg_hr: Mapped[int | None] = mapped_column(Integer)


class AppleWorkout(Base):
    """Auto-detected Watch/Health workouts (a run, a swim) — distinct from the
    manually-logged PPL sets in workout_session/set_log."""

    __tablename__ = "apple_workout"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(200), unique=True)
    workout_type: Mapped[str] = mapped_column(String(64))
    start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))
    active_kcal: Mapped[Numeric | None] = mapped_column(Numeric(7, 2))
    distance_km: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))
    avg_hr: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[int | None] = mapped_column(Integer)


# --- 7.8 Nutrition ---


class MealLog(Base):
    __tablename__ = "meal_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    meal_type: Mapped[str | None] = mapped_column(String(32))
    description_raw: Mapped[str | None] = mapped_column(Text)
    est_kcal: Mapped[int | None] = mapped_column(Integer)
    est_protein_g: Mapped[int | None] = mapped_column(Integer)
    est_carbs_g: Mapped[int | None] = mapped_column(Integer)
    est_fat_g: Mapped[int | None] = mapped_column(Integer)
    confirmed_bool: Mapped[bool] = mapped_column(Boolean, default=False)


class DailyNutrition(Base):
    __tablename__ = "daily_nutrition"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    kcal_target: Mapped[int | None] = mapped_column(Integer)
    kcal_actual: Mapped[int | None] = mapped_column(Integer)
    protein_actual: Mapped[int | None] = mapped_column(Integer)


# --- 7.9 Study ---


class StudyTopic(Base):
    __tablename__ = "study_topic"

    id: Mapped[int] = mapped_column(primary_key=True)
    cert: Mapped[str] = mapped_column(String(16))  # CKA|CKAD
    topic: Mapped[str] = mapped_column(String(200))
    target_hours: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))
    done_hours: Mapped[Numeric] = mapped_column(Numeric(6, 2), default=0)


class StudySession(Base):
    __tablename__ = "study_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("study_topic.id"))
    minutes: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)


# --- 7.10 Family Time ---


class FamilyEvent(Base):
    __tablename__ = "family_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(32))  # wife_evening|kids_activity|family_outing
    participants: Mapped[dict | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)


# --- 7.11 Memory ---


class JournalEntry(Base):
    __tablename__ = "journal_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    text: Mapped[str] = mapped_column(Text)  # PII, local-only
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))


class UserFact(Base):
    __tablename__ = "user_fact"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Numeric | None] = mapped_column(Numeric(3, 2))
    source_journal_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entry.id"))
    confirmed_bool: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class InteractionLog(Base):
    __tablename__ = "interaction_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    direction: Mapped[str] = mapped_column(String(8))  # in|out
    channel: Mapped[str] = mapped_column(String(32), default="telegram")
    agent: Mapped[str | None] = mapped_column(String(32))
    tokens_local: Mapped[int | None] = mapped_column(Integer)
    tokens_cloud: Mapped[int | None] = mapped_column(Integer)
    redaction_applied: Mapped[str | None] = mapped_column(String(200))


# --- 7.12 System ---


class NotificationPolicy(Base):
    __tablename__ = "notification_policy"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(120), unique=True)
    channel: Mapped[str] = mapped_column(String(16), default="telegram")
    quiet_hours_json: Mapped[dict | None] = mapped_column(JSON)


class AgentAudit(Base):
    __tablename__ = "agent_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    agent: Mapped[str] = mapped_column(String(32))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    tool_calls_json: Mapped[dict | None] = mapped_column(JSON)
    result_summary: Mapped[str | None] = mapped_column(Text)


# --- Saved places (not in original MASTER_SPEC schema; supports maps tools) ---


class SavedPlace(Base):
    __tablename__ = "saved_place"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    address: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
