"""Tests that make_executor's flat if/elif dispatch table actually forwards
each tool call to the right client function with the right argument names.
This is exactly the class of bug that's easy to introduce silently: rename
a kwarg in one place and not the other, and nothing fails loudly until the
model happens to call that specific tool.
"""

from unittest.mock import AsyncMock

import pytest

from app import tools


@pytest.fixture()
def executor():
    return tools.make_executor(12345)


async def test_unknown_tool_returns_error_string(executor):
    result = await executor("not_a_real_tool", {})
    assert result == "Unknown tool: not_a_real_tool"


async def test_get_driving_directions_dispatch(executor, monkeypatch):
    mock = AsyncMock(return_value="12 minutes to work")
    monkeypatch.setattr(tools.maps_client, "get_driving_directions", mock)

    result = await executor("get_driving_directions", {"destination": "work"})

    mock.assert_awaited_once_with(12345, "work")
    assert result == "12 minutes to work"


async def test_get_train_departures_dispatch_with_defaults(executor, monkeypatch):
    mock = AsyncMock(return_value="next train at 8:05")
    monkeypatch.setattr(tools.maps_client, "get_train_departures", mock)

    await executor("get_train_departures", {"origin_station": "Bochnia"})

    mock.assert_awaited_once_with("Bochnia", None, 4, None, None)


async def test_get_train_departures_dispatch_with_all_args(executor, monkeypatch):
    mock = AsyncMock(return_value="ok")
    monkeypatch.setattr(tools.maps_client, "get_train_departures", mock)

    await executor(
        "get_train_departures",
        {
            "origin_station": "Bochnia",
            "destination_station": "Krakow Glowny",
            "count": 2,
            "departure_time_iso": "2026-07-23T08:00:00",
        },
    )

    mock.assert_awaited_once_with("Bochnia", "Krakow Glowny", 2, "2026-07-23T08:00:00", None)


async def test_list_calendar_events_dispatch_defaults(executor, monkeypatch):
    mock = AsyncMock(return_value="no events")
    monkeypatch.setattr(tools.calendar_client, "list_upcoming_events", mock)

    await executor("list_calendar_events", {})

    mock.assert_awaited_once_with(7, "primary")


async def test_create_calendar_event_dispatch(executor, monkeypatch):
    mock = AsyncMock(return_value="created")
    monkeypatch.setattr(tools.calendar_client, "create_event", mock)

    await executor(
        "create_calendar_event",
        {"title": "Gym", "start_iso": "2026-07-23T18:00:00", "calendar": "family"},
    )

    mock.assert_awaited_once_with("Gym", "2026-07-23T18:00:00", None, "family", None)


async def test_log_expense_dispatch(executor, monkeypatch):
    mock = AsyncMock(return_value="logged")
    monkeypatch.setattr(tools.finance_client, "log_expense", mock)

    await executor(
        "log_expense", {"amount_pln": 42.5, "category": "groceries", "merchant": "Biedronka"}
    )

    mock.assert_awaited_once_with(42.5, "groceries", "Biedronka", None, None)


async def test_get_health_summary_dispatch_default_period(executor, monkeypatch):
    mock = AsyncMock(return_value="steps: 5000")
    monkeypatch.setattr(tools.health_client, "get_health_summary", mock)

    await executor("get_health_summary", {})

    mock.assert_awaited_once_with("week")
