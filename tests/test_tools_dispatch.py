"""Tests that make_executor's flat if/elif dispatch table actually forwards
each tool call to the right client function with the right argument names.
This is exactly the class of bug that's easy to introduce silently: rename
a kwarg in one place and not the other, and nothing fails loudly until the
model happens to call that specific tool.
"""

from unittest.mock import AsyncMock

import pytest

from app import tools
from app.ollama_client import TerminalToolResult


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


async def test_log_meal_dispatch(executor, monkeypatch):
    mock = AsyncMock(return_value="logged")
    monkeypatch.setattr(tools.nutrition_client, "log_meal", mock)

    await executor("log_meal", {"description": "chicken and rice", "est_kcal": 500})

    mock.assert_awaited_once_with("chicken and rice", 500, None, None, None, None)


async def test_get_daily_nutrition_dispatch_defaults(executor, monkeypatch):
    mock = AsyncMock(return_value="500 kcal")
    monkeypatch.setattr(tools.nutrition_client, "get_daily_nutrition", mock)

    await executor("get_daily_nutrition", {})

    mock.assert_awaited_once_with(None)


async def test_set_daily_target_dispatch(executor, monkeypatch):
    mock = AsyncMock(return_value="set")
    monkeypatch.setattr(tools.nutrition_client, "set_daily_target", mock)

    await executor("set_daily_target", {"kcal": 2000})

    mock.assert_awaited_once_with(2000, None)


async def test_consult_advanced_model_dispatch_records_cloud_usage(monkeypatch):
    mock = AsyncMock(return_value=("cloud reply", 77))
    monkeypatch.setattr(tools.reasoning_client, "consult", mock)

    usage: dict = {}
    executor_with_usage = tools.make_executor(12345, usage)
    result = await executor_with_usage(
        "consult_advanced_model", {"question": "what should I eat?", "context": "500kcal left"}
    )

    mock.assert_awaited_once_with("what should I eat?", "500kcal left")
    assert isinstance(result, TerminalToolResult)
    assert result.content == "cloud reply"
    assert usage["cloud_used"] is True
    assert usage["cloud_tokens"] == 77
    assert usage["tool_calls"] == [
        {
            "name": "consult_advanced_model",
            "args": {"question": "what should I eat?", "context": "500kcal left"},
        }
    ]


async def test_consult_advanced_model_dispatch_without_usage_tracker(executor, monkeypatch):
    mock = AsyncMock(return_value=("cloud reply", 10))
    monkeypatch.setattr(tools.reasoning_client, "consult", mock)

    result = await executor("consult_advanced_model", {"question": "what should I eat?"})

    assert isinstance(result, TerminalToolResult)
    assert result.content == "cloud reply"


async def test_consult_advanced_model_publishes_thinking_cloud_status(monkeypatch):
    monkeypatch.setattr(
        tools.reasoning_client, "consult", AsyncMock(return_value=("cloud reply", 10))
    )
    status_mock = AsyncMock()
    monkeypatch.setattr(tools.redis_client, "publish_status_event", status_mock)

    executor_with_status = tools.make_executor(12345, status_session_id=99)
    await executor_with_status("consult_advanced_model", {"question": "what should I eat?"})

    status_mock.assert_awaited_once_with(99, "thinking_cloud")


async def test_consult_advanced_model_skips_status_publish_when_no_session_given(
    executor, monkeypatch
):
    monkeypatch.setattr(
        tools.reasoning_client, "consult", AsyncMock(return_value=("cloud reply", 10))
    )
    status_mock = AsyncMock()
    monkeypatch.setattr(tools.redis_client, "publish_status_event", status_mock)

    await executor("consult_advanced_model", {"question": "what should I eat?"})

    status_mock.assert_not_awaited()


async def test_other_tools_do_not_publish_thinking_cloud_status(monkeypatch):
    monkeypatch.setattr(tools.health_client, "get_health_summary", AsyncMock(return_value="ok"))
    status_mock = AsyncMock()
    monkeypatch.setattr(tools.redis_client, "publish_status_event", status_mock)

    executor_with_status = tools.make_executor(12345, status_session_id=99)
    await executor_with_status("get_health_summary", {})

    status_mock.assert_not_awaited()


async def test_usage_records_every_real_tool_call_as_audit_trail(monkeypatch):
    """The audit trail (chat_message.tool_calls_json) must reflect what
    actually ran, not what the reply claims — see the live incident where
    the local model described creating calendar events it never called
    create_calendar_event for."""
    monkeypatch.setattr(tools.health_client, "get_health_summary", AsyncMock(return_value="ok"))
    monkeypatch.setattr(tools.finance_client, "get_spending_summary", AsyncMock(return_value="ok"))

    usage: dict = {}
    executor_with_usage = tools.make_executor(12345, usage)
    await executor_with_usage("get_health_summary", {"period": "week"})
    await executor_with_usage("get_spending_summary", {"period": "month"})

    assert usage["tool_calls"] == [
        {"name": "get_health_summary", "args": {"period": "week"}},
        {"name": "get_spending_summary", "args": {"period": "month"}},
    ]


async def test_usage_records_unknown_tool_calls_too(monkeypatch):
    usage: dict = {}
    executor_with_usage = tools.make_executor(12345, usage)

    await executor_with_usage("not_a_real_tool", {"foo": "bar"})

    assert usage["tool_calls"] == [{"name": "not_a_real_tool", "args": {"foo": "bar"}}]


async def test_no_usage_tracker_does_not_crash_dispatch(executor):
    # `executor` fixture has no usage dict at all — make_executor(12345).
    result = await executor("get_daily_nutrition", {})
    assert result is not None
