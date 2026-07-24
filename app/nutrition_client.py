"""Meal logging + daily calorie/protein tracking, backed by the MealLog/
DailyNutrition tables (MASTER_SPEC.md §7.8) — same shape as finance_client.py.
Qwen estimates macros itself from the description (it already reasons about
nutrition when asked); these tools just persist the estimate and roll it into
the day's total."""

import datetime as dt

from app.db import SessionLocal
from app.models import DailyNutrition, MealLog


def _get_or_create_daily(db, date: dt.date) -> DailyNutrition:
    row = db.get(DailyNutrition, date)
    if row is None:
        row = DailyNutrition(date=date)
        db.add(row)
        db.flush()
    return row


async def log_meal(
    description: str,
    est_kcal: int,
    est_protein_g: int | None = None,
    est_carbs_g: int | None = None,
    est_fat_g: int | None = None,
    meal_type: str | None = None,
) -> str:
    today = dt.date.today()
    with SessionLocal() as db:
        db.add(
            MealLog(
                ts=dt.datetime.now(dt.timezone.utc),
                meal_type=meal_type,
                description_raw=description,
                est_kcal=est_kcal,
                est_protein_g=est_protein_g,
                est_carbs_g=est_carbs_g,
                est_fat_g=est_fat_g,
                confirmed_bool=True,
            )
        )
        daily = _get_or_create_daily(db, today)
        daily.kcal_actual = (daily.kcal_actual or 0) + est_kcal
        if est_protein_g:
            daily.protein_actual = (daily.protein_actual or 0) + est_protein_g
        db.commit()

    macro_bits = []
    if est_protein_g:
        macro_bits.append(f"{est_protein_g}g protein")
    if est_carbs_g:
        macro_bits.append(f"{est_carbs_g}g carbs")
    if est_fat_g:
        macro_bits.append(f"{est_fat_g}g fat")
    macro_note = f" ({', '.join(macro_bits)})" if macro_bits else ""
    return f"Logged '{description}' — ~{est_kcal} kcal{macro_note}."


async def get_daily_nutrition(date_iso: str | None = None) -> str:
    date = dt.date.fromisoformat(date_iso) if date_iso else dt.date.today()
    with SessionLocal() as db:
        row = db.get(DailyNutrition, date)

    if row is None or (row.kcal_target is None and row.kcal_actual is None):
        return f"No nutrition data for {date.isoformat()} yet."

    lines = []
    if row.kcal_actual is not None:
        lines.append(f"{row.kcal_actual} kcal logged so far")
    else:
        lines.append("0 kcal logged so far")
    if row.kcal_target is not None:
        remaining = row.kcal_target - (row.kcal_actual or 0)
        lines.append(f"target {row.kcal_target} kcal ({remaining} remaining)")
    if row.protein_actual is not None:
        lines.append(f"{row.protein_actual}g protein logged")

    return f"Nutrition for {date.isoformat()}: " + ", ".join(lines) + "."


async def set_daily_target(kcal: int, date_iso: str | None = None) -> str:
    """Sets the day's kcal target. daily_nutrition has no protein_target column
    (only protein_actual, i.e. consumed) — only calories are settable here."""
    date = dt.date.fromisoformat(date_iso) if date_iso else dt.date.today()
    with SessionLocal() as db:
        daily = _get_or_create_daily(db, date)
        daily.kcal_target = kcal
        db.commit()
    return f"Set {date.isoformat()}'s calorie target to {kcal} kcal."
