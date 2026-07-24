import datetime as dt

from app import nutrition_client
from app.db import SessionLocal
from app.models import DailyNutrition, MealLog


async def test_log_meal_persists_and_accumulates_daily_actual():
    await nutrition_client.log_meal("chicken and rice", 500, est_protein_g=40)
    await nutrition_client.log_meal("apple", 100)

    with SessionLocal() as db:
        logs = db.query(MealLog).order_by(MealLog.id).all()
        daily = db.get(DailyNutrition, dt.date.today())

    assert [l.description_raw for l in logs] == ["chicken and rice", "apple"]
    assert logs[0].est_protein_g == 40
    assert daily.kcal_actual == 600
    assert daily.protein_actual == 40


async def test_get_daily_nutrition_reports_remaining_budget():
    await nutrition_client.set_daily_target(2000)
    await nutrition_client.log_meal("breakfast", 500)

    result = await nutrition_client.get_daily_nutrition()

    assert "500 kcal logged" in result
    assert "target 2000 kcal" in result
    assert "1500 remaining" in result


async def test_get_daily_nutrition_with_no_data_says_so():
    result = await nutrition_client.get_daily_nutrition("2020-01-01")
    assert "No nutrition data for 2020-01-01" in result


async def test_set_daily_target_is_idempotent_per_date():
    await nutrition_client.set_daily_target(1800)
    await nutrition_client.set_daily_target(2200)

    with SessionLocal() as db:
        rows = db.query(DailyNutrition).all()
    assert len(rows) == 1
    assert rows[0].kcal_target == 2200
