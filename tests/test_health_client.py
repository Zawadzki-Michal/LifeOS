"""health_client parses Apple Health webhook payloads into the DB — no
external API calls, so these are pure logic/DB tests. Several cases here are
direct regressions for real bugs caught by manual testing (see
02-PROGRESS.md §4): active/basal energy arriving in kJ not kcal, and
sleep_analysis's totalSleep arriving in hours already, not minutes.
"""

import datetime as dt

from app import health_client
from app.db import SessionLocal
from app.models import AppleWorkout, Goal, MetricDaily


def _metric(name, qty, units="", date="2026-07-20 08:00:00 +0200"):
    return {"name": name, "units": units, "data": [{"date": date, "qty": qty}]}


async def test_active_energy_in_kj_converted_to_kcal():
    # 4184 kJ == 1000 kcal exactly (kcal = kJ / 4.184).
    payload = {"data": {"metrics": [_metric("active_energy", 4184, units="kJ")]}}
    await health_client.ingest_payload(payload)

    with SessionLocal() as db:
        row = db.get(MetricDaily, dt.date(2026, 7, 20))
    assert round(float(row.active_kcal)) == 1000


async def test_active_energy_already_in_kcal_not_double_converted():
    payload = {"data": {"metrics": [_metric("active_energy", 500, units="kcal")]}}
    await health_client.ingest_payload(payload)

    with SessionLocal() as db:
        row = db.get(MetricDaily, dt.date(2026, 7, 20))
    assert float(row.active_kcal) == 500


async def test_basal_energy_in_kj_converted_to_kcal():
    payload = {"data": {"metrics": [_metric("basal_energy_burned", 4184, units="kJ")]}}
    await health_client.ingest_payload(payload)

    with SessionLocal() as db:
        row = db.get(MetricDaily, dt.date(2026, 7, 20))
    assert round(float(row.resting_kcal)) == 1000


async def test_sleep_totalsleep_in_hours_not_divided_by_60():
    payload = {
        "data": {
            "metrics": [
                {
                    "name": "sleep_analysis",
                    "units": "hr",
                    "data": [{"date": "2026-07-20 08:00:00 +0200", "totalSleep": 7.5}],
                }
            ]
        }
    }
    await health_client.ingest_payload(payload)

    with SessionLocal() as db:
        row = db.get(MetricDaily, dt.date(2026, 7, 20))
    assert float(row.sleep_hours) == 7.5


async def test_sleep_totalsleep_in_minutes_converted_to_hours():
    payload = {
        "data": {
            "metrics": [
                {
                    "name": "sleep_analysis",
                    "units": "min",
                    "data": [{"date": "2026-07-20 08:00:00 +0200", "totalSleep": 450}],
                }
            ]
        }
    }
    await health_client.ingest_payload(payload)

    with SessionLocal() as db:
        row = db.get(MetricDaily, dt.date(2026, 7, 20))
    assert float(row.sleep_hours) == 7.5


async def test_step_count_accumulates_multiple_entries_same_day():
    payload = {
        "data": {
            "metrics": [
                {
                    "name": "step_count",
                    "units": "count",
                    "data": [
                        {"date": "2026-07-20 08:00:00 +0200", "qty": 3000},
                        {"date": "2026-07-20 18:00:00 +0200", "qty": 4500},
                    ],
                }
            ]
        }
    }
    await health_client.ingest_payload(payload)

    with SessionLocal() as db:
        row = db.get(MetricDaily, dt.date(2026, 7, 20))
    assert row.steps == 7500


async def test_reingesting_same_workout_does_not_duplicate():
    workout = {
        "id": "abc-123",
        "name": "Functional Strength Training",
        "start": "2026-07-20 07:00:00 +0200",
        "end": "2026-07-20 07:45:00 +0200",
        "activeEnergyBurned": {"qty": 300, "units": "kcal"},
    }
    payload = {"data": {"metrics": [], "workouts": [workout]}}

    first = await health_client.ingest_payload(payload)
    assert "1 new workout" in first

    second = await health_client.ingest_payload(payload)
    assert "0 new workout" in second

    with SessionLocal() as db:
        count = db.query(AppleWorkout).filter(AppleWorkout.external_id == "abc-123").count()
    assert count == 1


async def test_workout_active_energy_kj_converted():
    workout = {
        "id": "kj-workout",
        "name": "Run",
        "start": "2026-07-20 07:00:00 +0200",
        "end": "2026-07-20 07:30:00 +0200",
        "activeEnergyBurned": {"qty": 4184, "units": "kJ"},
    }
    await health_client.ingest_payload({"data": {"metrics": [], "workouts": [workout]}})

    with SessionLocal() as db:
        record = db.query(AppleWorkout).filter(AppleWorkout.external_id == "kj-workout").one()
    assert round(float(record.active_kcal)) == 1000


def test_get_health_summary_reports_step_and_sleep_averages():
    with SessionLocal() as db:
        db.add(MetricDaily(date=dt.date.today(), steps=5000, sleep_hours=7))
        db.add(MetricDaily(date=dt.date.today() - dt.timedelta(days=1), steps=7000, sleep_hours=6))
        db.commit()

    import asyncio

    summary = asyncio.run(health_client.get_health_summary("week"))
    assert "12000 total" in summary
    assert "6000/day avg" in summary
    assert "6.5 hrs/night avg" in summary


def test_check_sync_health_warns_after_two_day_gap():
    import asyncio

    with SessionLocal() as db:
        db.add(MetricDaily(date=dt.date.today() - dt.timedelta(days=3)))
        db.commit()

    warnings = asyncio.run(health_client.check_sync_health())
    assert len(warnings) == 1
    assert "3 days ago" in warnings[0]


def test_check_sync_health_silent_when_recent():
    import asyncio

    with SessionLocal() as db:
        db.add(MetricDaily(date=dt.date.today()))
        db.commit()

    assert asyncio.run(health_client.check_sync_health()) == []


def test_workout_goal_progress_matches_by_keyword():
    import asyncio

    with SessionLocal() as db:
        db.add(Goal(kind="frequency", title="Squash sessions", target_value="2", status="active"))
        db.add(Goal(kind="frequency", title="Gym sessions", target_value="3", status="active"))
        now = dt.datetime.now(dt.timezone.utc)
        db.add(
            AppleWorkout(
                external_id="w1",
                workout_type="Squash",
                start=now,
                end=now + dt.timedelta(hours=1),
            )
        )
        db.add(
            AppleWorkout(
                external_id="w2",
                workout_type="Functional Strength Training",
                start=now,
                end=now + dt.timedelta(hours=1),
            )
        )
        db.commit()

    result = asyncio.run(health_client.get_workout_goal_progress())
    assert "Squash sessions: 1 this week (target 2)" in result
    assert "Gym sessions: 1 this week (target 3)" in result


def test_parse_ts_handles_space_separator_with_offset():
    result = health_client._parse_ts("2026-07-20 08:00:00 +0200")
    assert result == dt.datetime(2026, 7, 20, 8, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))


def test_parse_ts_handles_z_suffix():
    result = health_client._parse_ts("2026-07-20T08:00:00Z")
    assert result == dt.datetime(2026, 7, 20, 8, 0, 0, tzinfo=dt.timezone.utc)


def test_parse_ts_falls_back_to_date_only():
    result = health_client._parse_ts("2026-07-20")
    assert result.date() == dt.date(2026, 7, 20)


def test_parse_ts_returns_none_for_garbage():
    assert health_client._parse_ts("not a date") is None
