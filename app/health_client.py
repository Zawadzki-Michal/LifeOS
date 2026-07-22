"""Ingests Health Auto Export's REST API JSON payload (see
https://github.com/Lybron/health-auto-export/wiki/API-Export---JSON-Format)
into metric_daily / apple_workout, and exposes a get_health_summary tool."""

import datetime as dt
import logging
import re
from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.models import AppleWorkout, Goal, MetricDaily

logger = logging.getLogger("lifeos.health")

TZ = ZoneInfo("Europe/Warsaw")

_GYM_KEYWORDS = ("strength", "silow", "functional", "gym", "hiit", "cross")
_SQUASH_KEYWORDS = ("squash",)

_TS_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T](?P<time>\d{2}:\d{2}:\d{2})\s*"
    r"(?P<sign>[+-])(?P<oh>\d{2}):?(?P<om>\d{2})$"
)

_KNOWN_METRICS = {
    "step_count",
    "steps",
    "active_energy",
    "active_energy_burned",
    "basal_energy_burned",
    "resting_energy",
    "resting_heart_rate",
    "heart_rate",
    "heart_rate_variability",
    "heart_rate_variability_sdnn",
    "hrv",
    "sleep_analysis",
    "weight_body_mass",
    "body_mass",
    # Not stored yet (no matching column) but recognized so they don't spam
    # the "unrecognized metric" log — real fields Health Auto Export sends.
    "apple_exercise_time",
    "apple_stand_time",
    "respiratory_rate",
}

_KCAL_PER_KJ = 1 / 4.184


def _energy_to_kcal(qty: float, units: str) -> float:
    if (units or "").strip().lower() in ("kj", "kilojoule", "kilojoules"):
        return qty * _KCAL_PER_KJ
    return qty


def _sleep_value_to_hours(value: float, units: str) -> float:
    if (units or "").strip().lower() in ("hr", "hour", "hours", "h"):
        return float(value)
    return float(value) / 60


def _parse_ts(raw: str) -> dt.datetime | None:
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+0000"
    m = _TS_RE.match(s)
    if m:
        iso = f"{m['date']}T{m['time']}{m['sign']}{m['oh']}:{m['om']}"
        return dt.datetime.fromisoformat(iso)
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _qty(field) -> float | None:
    if isinstance(field, dict):
        return field.get("qty")
    return field


def _qty_energy_kcal(field) -> float | None:
    if not isinstance(field, dict):
        return field
    qty = field.get("qty")
    if qty is None:
        return None
    return _energy_to_kcal(qty, field.get("units", ""))


def _period_start_date(period: str) -> tuple[dt.date, str]:
    today = dt.datetime.now(TZ).date()
    if period == "today":
        return today, "today"
    if period == "month":
        return today.replace(day=1), "this month"
    return today - dt.timedelta(days=today.weekday()), "this week"


async def ingest_payload(payload: dict) -> str:
    data = payload.get("data", {})
    metrics = data.get("metrics", [])
    workouts = data.get("workouts", [])

    daily: dict[dt.date, dict] = {}

    for metric in metrics:
        mname = (metric.get("name") or "").strip().lower()
        munits = metric.get("units", "")
        for entry in metric.get("data", []):
            date_raw = entry.get("date")
            ts = _parse_ts(date_raw) if date_raw else None
            if ts is None:
                continue
            day = ts.astimezone(TZ).date()
            bucket = daily.setdefault(day, {})

            if mname in ("step_count", "steps"):
                bucket["steps"] = bucket.get("steps", 0) + (entry.get("qty") or 0)
            elif mname in ("active_energy", "active_energy_burned"):
                qty = entry.get("qty")
                if qty is not None:
                    bucket["active_kcal"] = bucket.get("active_kcal", 0) + _energy_to_kcal(qty, munits)
            elif mname in ("basal_energy_burned", "resting_energy"):
                qty = entry.get("qty")
                if qty is not None:
                    bucket["resting_kcal"] = bucket.get("resting_kcal", 0) + _energy_to_kcal(qty, munits)
            elif mname == "resting_heart_rate" and entry.get("qty") is not None:
                bucket.setdefault("_resting_hr", []).append(entry["qty"])
            elif mname == "heart_rate":
                avg = entry.get("Avg", entry.get("avg", entry.get("qty")))
                if avg is not None:
                    bucket.setdefault("_avg_hr", []).append(avg)
            elif mname in ("heart_rate_variability", "heart_rate_variability_sdnn", "hrv"):
                if entry.get("qty") is not None:
                    bucket.setdefault("_hrv", []).append(entry["qty"])
            elif mname == "sleep_analysis":
                sleep_val = entry.get("totalSleep", entry.get("asleep"))
                if sleep_val is not None:
                    bucket["sleep_hours"] = round(_sleep_value_to_hours(sleep_val, munits), 2)
            elif mname in ("weight_body_mass", "body_mass") and entry.get("qty") is not None:
                bucket["weight_kg"] = entry["qty"]

    unknown = sorted({(m.get("name") or "?").lower() for m in metrics} - _KNOWN_METRICS)
    if unknown:
        logger.info("Ignoring unrecognized Health Auto Export metrics: %s", unknown)

    with SessionLocal() as db:
        for day, vals in daily.items():
            row = db.get(MetricDaily, day)
            if row is None:
                row = MetricDaily(date=day)
                db.add(row)
            if "steps" in vals:
                row.steps = int(vals["steps"])
            if "active_kcal" in vals:
                row.active_kcal = round(vals["active_kcal"], 2)
            if "resting_kcal" in vals:
                row.resting_kcal = round(vals["resting_kcal"], 2)
            if "sleep_hours" in vals:
                row.sleep_hours = vals["sleep_hours"]
            if "weight_kg" in vals:
                row.weight_kg = vals["weight_kg"]
            if vals.get("_resting_hr"):
                row.resting_hr = round(sum(vals["_resting_hr"]) / len(vals["_resting_hr"]))
            if vals.get("_avg_hr"):
                row.avg_hr = round(sum(vals["_avg_hr"]) / len(vals["_avg_hr"]))
            if vals.get("_hrv"):
                row.hrv = round(sum(vals["_hrv"]) / len(vals["_hrv"]))

        new_workouts = 0
        for w in workouts:
            ext_id = str(w.get("id") or f"{w.get('name', 'workout')}-{w.get('start', '')}")
            start = _parse_ts(w["start"]) if w.get("start") else None
            end = _parse_ts(w["end"]) if w.get("end") else None
            if start is None or end is None:
                continue

            duration_raw = w.get("duration")
            duration_min = (
                round(duration_raw / 60, 2) if duration_raw else round((end - start).total_seconds() / 60, 2)
            )

            record = db.query(AppleWorkout).filter(AppleWorkout.external_id == ext_id).first()
            is_new = record is None
            if record is None:
                record = AppleWorkout(external_id=ext_id)
                db.add(record)
            record.workout_type = w.get("name", "Workout")
            record.start = start
            record.end = end
            record.duration_min = duration_min
            record.active_kcal = _qty_energy_kcal(w.get("activeEnergyBurned"))
            record.distance_km = _qty(w.get("distance"))
            record.avg_hr = _qty(w.get("avgHeartRate"))
            record.max_hr = _qty(w.get("maxHeartRate"))
            if is_new:
                new_workouts += 1

        db.commit()

    return f"Synced {len(daily)} day(s) of metrics, {new_workouts} new workout(s)."


async def get_health_summary(period: str = "week") -> str:
    start_date, label = _period_start_date(period)
    start_dt_utc = dt.datetime.combine(start_date, dt.time.min, tzinfo=TZ).astimezone(dt.timezone.utc)

    with SessionLocal() as db:
        rows = db.query(MetricDaily).filter(MetricDaily.date >= start_date).order_by(MetricDaily.date).all()
        workouts = db.query(AppleWorkout).filter(AppleWorkout.start >= start_dt_utc).all()

    if not rows and not workouts:
        return f"No Apple Health data synced {label} yet."

    total_steps = sum(r.steps or 0 for r in rows)
    days_with_steps = [r for r in rows if r.steps is not None]
    avg_steps = round(total_steps / len(days_with_steps)) if days_with_steps else 0
    total_active_kcal = sum(float(r.active_kcal) for r in rows if r.active_kcal is not None)
    sleep_vals = [float(r.sleep_hours) for r in rows if r.sleep_hours is not None]
    avg_sleep = round(sum(sleep_vals) / len(sleep_vals), 1) if sleep_vals else None
    resting_hr_vals = [r.resting_hr for r in rows if r.resting_hr is not None]
    avg_resting_hr = round(sum(resting_hr_vals) / len(resting_hr_vals)) if resting_hr_vals else None

    lines = [f"Steps: {total_steps} total, {avg_steps}/day avg"]
    if total_active_kcal:
        lines.append(f"Active energy: {total_active_kcal:.0f} kcal total")
    if avg_sleep is not None:
        lines.append(f"Sleep: {avg_sleep} hrs/night avg")
    if avg_resting_hr is not None:
        lines.append(f"Resting heart rate: {avg_resting_hr} bpm avg")

    if workouts:
        by_type: dict[str, int] = {}
        for w in workouts:
            by_type[w.workout_type] = by_type.get(w.workout_type, 0) + 1
        workout_str = ", ".join(f"{n}x {t}" for t, n in by_type.items())
        lines.append(f"Workouts: {len(workouts)} ({workout_str})")
    else:
        lines.append("Workouts: none logged")

    return f"Health summary ({label}):\n" + "\n".join(lines)


async def get_daily_snapshot(date: dt.date) -> str | None:
    """Internal helper for the scheduler's morning/evening messages — a short
    plain-text summary of one day, or None if nothing was synced for it."""
    with SessionLocal() as db:
        row = db.get(MetricDaily, date)
        workouts = (
            db.query(AppleWorkout)
            .filter(
                AppleWorkout.start >= dt.datetime.combine(date, dt.time.min, tzinfo=TZ),
                AppleWorkout.start < dt.datetime.combine(date + dt.timedelta(days=1), dt.time.min, tzinfo=TZ),
            )
            .all()
        )

    if row is None and not workouts:
        return None

    parts = []
    if row and row.steps is not None:
        parts.append(f"{row.steps} steps")
    if row and row.active_kcal is not None:
        parts.append(f"{float(row.active_kcal):.0f} kcal active")
    if row and row.sleep_hours is not None:
        parts.append(f"{float(row.sleep_hours):.1f}h sleep")
    if row and row.resting_hr is not None:
        parts.append(f"resting HR {row.resting_hr} bpm")
    if workouts:
        parts.append(", ".join(w.workout_type for w in workouts) + " workout")

    return ", ".join(parts) if parts else None


async def get_workout_goal_progress() -> str | None:
    """Cross-references this week's synced workouts against the Gym/Squash
    frequency goals, so the scheduler can nudge with real numbers ('1/3 squash
    sessions this week') instead of generic 'move more' advice. Wife-time and
    Kids-activity goals aren't covered here — those track family_event, which
    nothing logs into yet, not Apple Health workouts."""
    week_start, _ = _period_start_date("week")
    start_utc = dt.datetime.combine(week_start, dt.time.min, tzinfo=TZ).astimezone(dt.timezone.utc)

    with SessionLocal() as db:
        goals = (
            db.query(Goal)
            .filter(Goal.kind == "frequency", Goal.status == "active")
            .all()
        )
        workouts = db.query(AppleWorkout).filter(AppleWorkout.start >= start_utc).all()

    if not goals:
        return None

    gym_count = sum(1 for w in workouts if any(k in w.workout_type.lower() for k in _GYM_KEYWORDS))
    squash_count = sum(1 for w in workouts if any(k in w.workout_type.lower() for k in _SQUASH_KEYWORDS))

    lines = []
    for g in goals:
        title_lower = g.title.lower()
        if "squash" in title_lower:
            lines.append(f"{g.title}: {squash_count} this week (target {g.target_value})")
        elif "gym" in title_lower:
            lines.append(f"{g.title}: {gym_count} this week (target {g.target_value})")

    return "; ".join(lines) if lines else None


async def get_latest_weight() -> str | None:
    """Most recent synced weight reading, for referencing against the weight
    goal — Apple Health sync populates metric_daily.weight_kg once 'Weight'
    is added to the app's selected metrics."""
    with SessionLocal() as db:
        row = (
            db.query(MetricDaily)
            .filter(MetricDaily.weight_kg.isnot(None))
            .order_by(MetricDaily.date.desc())
            .first()
        )
    if row is None:
        return None
    return f"{float(row.weight_kg):.1f} kg (as of {row.date.isoformat()})"


async def check_sync_health() -> list[str]:
    """Returns a warning if Health data hasn't synced in a while — otherwise
    a broken automation (expired token, iOS killing background refresh) would
    go unnoticed indefinitely."""
    with SessionLocal() as db:
        latest = db.query(MetricDaily).order_by(MetricDaily.date.desc()).first()

    if latest is None:
        return []

    gap_days = (dt.date.today() - latest.date).days
    if gap_days >= 2:
        return [
            f"Heads up — no Apple Health data has synced since {latest.date.isoformat()} "
            f"({gap_days} days ago). Worth checking the Health Auto Export automation on your phone."
        ]
    return []
