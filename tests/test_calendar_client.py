"""calendar_client hits the Google Calendar API — respx mocks the HTTP layer.
list_today_events's past/upcoming labeling gets its own test since the code
comment explicitly notes the model couldn't reliably work this out itself
from a separate current-time line, which is why it's computed here instead.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import httpx
import respx

from app import calendar_client, redis_client
from app.calendar_client import CALENDAR_API_BASE, TOKEN_URL

TZ = ZoneInfo("Europe/Warsaw")


async def test_not_configured_short_circuits_without_http_call(monkeypatch, respx_mock):
    monkeypatch.setattr(calendar_client.settings, "google_calendar_refresh_token", "")
    reply = await calendar_client.list_upcoming_events()
    assert "isn't connected yet" in reply
    assert not respx_mock.calls.called


@respx.mock
async def test_get_access_token_uses_redis_cache_when_present():
    await redis_client.set_cached_access_token("cached-token-value")
    route = respx.post(TOKEN_URL)

    token = await calendar_client._get_access_token()

    assert token == "cached-token-value"
    assert not route.called


@respx.mock
async def test_get_access_token_fetches_and_caches_when_absent():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "fresh-token"})
    )

    token = await calendar_client._get_access_token()

    assert token == "fresh-token"
    cached = await redis_client.get_cached_access_token()
    assert cached == "fresh-token"


@respx.mock
async def test_resolve_calendar_id_primary_shortcut_skips_http():
    route = respx.get(f"{CALENDAR_API_BASE}/users/me/calendarList")
    cal_id = await calendar_client._resolve_calendar_id("primary")
    assert cal_id == "primary"
    assert not route.called


@respx.mock
async def test_resolve_calendar_id_matches_by_name_case_insensitive():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{CALENDAR_API_BASE}/users/me/calendarList").mock(
        return_value=httpx.Response(
            200, json={"items": [{"summary": "Family", "id": "family-cal-id"}]}
        )
    )

    cal_id = await calendar_client._resolve_calendar_id("FAMILY")
    assert cal_id == "family-cal-id"


@respx.mock
async def test_resolve_calendar_id_falls_back_to_primary_when_not_found():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{CALENDAR_API_BASE}/users/me/calendarList").mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    cal_id = await calendar_client._resolve_calendar_id("nonexistent")
    assert cal_id == "primary"


@respx.mock
async def test_list_upcoming_events_empty():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{CALENDAR_API_BASE}/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    reply = await calendar_client.list_upcoming_events(days_ahead=7)
    assert "No events in the next 7 days" in reply


@respx.mock
async def test_list_upcoming_events_formats_id_title_and_start():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{CALENDAR_API_BASE}/calendars/primary/events").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "evt-1",
                        "summary": "Gym",
                        "start": {"dateTime": "2026-07-23T18:00:00+02:00"},
                    }
                ]
            },
        )
    )

    reply = await calendar_client.list_upcoming_events()
    assert "[evt-1] Gym" in reply
    assert "2026-07-23T18:00:00+02:00" in reply


@respx.mock
async def test_create_event_defaults_end_to_one_hour_after_start():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    route = respx.post(f"{CALENDAR_API_BASE}/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"id": "new-evt"})
    )

    reply = await calendar_client.create_event("Gym", "2026-07-23T18:00:00")

    sent_body = respx_json(route)
    assert sent_body["start"]["dateTime"] == "2026-07-23T18:00:00"
    assert sent_body["end"]["dateTime"] == "2026-07-23T19:00:00"
    assert "new-evt" in reply
    # Must report back exactly what was sent, not whatever Google echoes —
    # see the timezone-display bug this guards against in calendar_client.py.
    assert "2026-07-23T18:00:00 to 2026-07-23T19:00:00" in reply


@respx.mock
async def test_create_event_includes_location_when_given():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    route = respx.post(f"{CALENDAR_API_BASE}/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"id": "new-evt"})
    )

    await calendar_client.create_event(
        "Gym", "2026-07-23T18:00:00", "2026-07-23T19:00:00", location="Backbase Office"
    )

    assert respx_json(route)["location"] == "Backbase Office"


async def test_update_event_with_no_fields_makes_no_http_call(respx_mock):
    reply = await calendar_client.update_event("evt-1")
    assert reply == "Nothing to update."
    assert not respx_mock.calls.called


@respx.mock
async def test_update_event_only_sends_provided_fields():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    route = respx.patch(f"{CALENDAR_API_BASE}/calendars/primary/events/evt-1").mock(
        return_value=httpx.Response(200, json={"id": "evt-1"})
    )

    reply = await calendar_client.update_event("evt-1", title="New title")

    body = respx_json(route)
    assert body == {"summary": "New title"}
    assert "title -> 'New title'" in reply


@respx.mock
async def test_update_event_404_returns_friendly_message():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.patch(f"{CALENDAR_API_BASE}/calendars/primary/events/missing").mock(
        return_value=httpx.Response(404, json={})
    )

    reply = await calendar_client.update_event("missing", title="x")
    assert "No event found with id missing" in reply


@respx.mock
async def test_delete_event_success():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.delete(f"{CALENDAR_API_BASE}/calendars/primary/events/evt-1").mock(
        return_value=httpx.Response(204)
    )

    reply = await calendar_client.delete_event("evt-1")
    assert reply == "Event deleted."


@respx.mock
async def test_delete_event_404_returns_friendly_message():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.delete(f"{CALENDAR_API_BASE}/calendars/primary/events/missing").mock(
        return_value=httpx.Response(404, json={})
    )

    reply = await calendar_client.delete_event("missing")
    assert "No event found with id missing" in reply


@respx.mock
async def test_list_today_events_labels_past_and_upcoming_correctly():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{CALENDAR_API_BASE}/users/me/calendarList").mock(
        return_value=httpx.Response(
            200, json={"items": [{"summary": "family", "id": "family-cal-id"}]}
        )
    )

    now = dt.datetime.now(TZ)
    past_start = (now - dt.timedelta(hours=1)).isoformat()
    future_start = (now + dt.timedelta(hours=1)).isoformat()

    respx.get(f"{CALENDAR_API_BASE}/calendars/primary/events").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"summary": "Already happened", "start": {"dateTime": past_start}},
                    {"summary": "Coming up", "start": {"dateTime": future_start}},
                ]
            },
        )
    )
    respx.get(f"{CALENDAR_API_BASE}/calendars/family-cal-id/events").mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    reply = await calendar_client.list_today_events()

    assert "Already happened" in reply
    assert "already started/passed" in reply
    assert "Coming up" in reply
    assert "(upcoming)" in reply


def respx_json(route):
    import json

    return json.loads(route.calls.last.request.content)
