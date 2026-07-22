"""maps_client hits Google's Directions API for both driving directions and
(via the transit mode) train departures. respx mocks the HTTP layer so these
tests exercise the real URL/param construction and response parsing without
a network call. The arrival_time_iso sorting test is a direct regression for
a real bug (see 02-PROGRESS.md): it used to return the earliest departures
hours before the deadline instead of the latest ones that still make it.
"""

import datetime as dt

import httpx
import respx

from app import maps_client, redis_client
from app.maps_client import DIRECTIONS_URL


def _driving_response(duration_text="20 mins", distance_text="15 km"):
    return {
        "status": "OK",
        "routes": [
            {
                "legs": [
                    {
                        "duration": {"text": duration_text, "value": 1200},
                        "distance": {"text": distance_text, "value": 15000},
                    }
                ]
            }
        ],
    }


def _transit_step(ts: int, line: str, departs_text: str, arrives_text: str):
    return {
        "travel_mode": "TRANSIT",
        "transit_details": {
            "line": {"short_name": line},
            "departure_time": {"value": ts, "text": departs_text},
            "arrival_time": {"value": ts + 1800, "text": arrives_text},
        },
    }


def _transit_response(departures: list[tuple[int, str, str, str]]):
    return {
        "status": "OK",
        "routes": [
            {
                "legs": [
                    {
                        "duration": {"text": "30 mins"},
                        "steps": [_transit_step(ts, line, dep_text, arr_text)],
                    }
                ]
            }
            for ts, line, dep_text, arr_text in departures
        ],
    }


async def test_no_location_cached_prompts_to_share_it(respx_mock):
    reply = await maps_client.get_driving_directions(999, "work")
    assert "don't have your current location" in reply
    assert not respx_mock.calls.called


async def test_no_maps_api_key_configured(monkeypatch):
    monkeypatch.setattr(maps_client.settings, "google_maps_api_key", "")
    reply = await maps_client.get_driving_directions(999, "work")
    assert "isn't configured yet" in reply


@respx.mock
async def test_successful_driving_directions_includes_maps_link():
    await redis_client.set_location(555, 50.1, 20.0)
    respx.get(DIRECTIONS_URL).mock(
        return_value=httpx.Response(200, json=_driving_response("18 mins", "12 km"))
    )

    reply = await maps_client.get_driving_directions(555, "work")

    assert "18 mins" in reply
    assert "12 km" in reply
    assert "google.com/maps/dir" in reply


@respx.mock
async def test_driving_directions_resolves_saved_place_name():
    await redis_client.set_location(555, 50.1, 20.0)
    await maps_client.upsert_saved_place("mom", "123 Real Address, Krakow")
    route = respx.get(DIRECTIONS_URL).mock(
        return_value=httpx.Response(200, json=_driving_response())
    )

    await maps_client.get_driving_directions(555, "mom")

    sent_destination = route.calls.last.request.url.params["destination"]
    assert sent_destination == "123 Real Address, Krakow"


@respx.mock
async def test_driving_directions_zero_results_status():
    await redis_client.set_location(555, 50.1, 20.0)
    respx.get(DIRECTIONS_URL).mock(
        return_value=httpx.Response(200, json={"status": "ZERO_RESULTS", "routes": []})
    )

    reply = await maps_client.get_driving_directions(555, "nowhere")
    assert "Couldn't find driving directions" in reply
    assert "ZERO_RESULTS" in reply


async def test_train_departures_no_maps_api_key(monkeypatch):
    monkeypatch.setattr(maps_client.settings, "google_maps_api_key", "")
    reply = await maps_client.get_train_departures("Bochnia", None)
    assert "isn't configured yet" in reply


async def test_train_departures_unknown_origin_without_destination(respx_mock):
    reply = await maps_client.get_train_departures("Some Random Town", None)
    assert "need a destination station" in reply
    assert not respx_mock.calls.called


@respx.mock
async def test_train_departures_defaults_destination_from_known_commute():
    route = respx.get(DIRECTIONS_URL).mock(
        return_value=httpx.Response(200, json=_transit_response([]))
    )

    await maps_client.get_train_departures("Bochnia", None)

    sent = route.calls.last.request.url.params
    assert sent["destination"] == "Kraków Główny, Poland"


@respx.mock
async def test_train_departures_no_time_given_uses_now():
    route = respx.get(DIRECTIONS_URL).mock(
        return_value=httpx.Response(200, json=_transit_response([]))
    )

    await maps_client.get_train_departures("Bochnia", "Kraków Główny")

    assert route.calls.last.request.url.params["departure_time"] == "now"


@respx.mock
async def test_train_departures_non_ok_status_returns_helpful_error():
    respx.get(DIRECTIONS_URL).mock(
        return_value=httpx.Response(200, json={"status": "ZERO_RESULTS", "routes": []})
    )

    reply = await maps_client.get_train_departures("Bochnia", "Kraków Główny")
    assert "Couldn't find a train" in reply
    assert "ZERO_RESULTS" in reply


@respx.mock
async def test_train_departures_dedups_same_departure_timestamp():
    same_ts = 1_800_000_000
    respx.get(DIRECTIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_transit_response(
                [
                    (same_ts, "R1", "08:00", "08:30"),
                    (same_ts, "R1", "08:00", "08:30"),  # duplicate route, same departure
                ]
            ),
        )
    )

    reply = await maps_client.get_train_departures("Bochnia", "Kraków Główny")
    assert reply.count("R1 departs") == 1


@respx.mock
async def test_arrival_time_returns_latest_departures_that_still_make_it():
    # Regression test: given a deadline, the tool must return the LATEST
    # departures that still arrive in time (maximizing prep/sleep time), not
    # the earliest ones hours before the deadline — that was the real bug.
    base = int(dt.datetime(2026, 7, 23, 6, 0, tzinfo=dt.timezone.utc).timestamp())
    departures = [
        (base, "EARLY", "06:00", "06:30"),
        (base + 3600, "MID", "07:00", "07:30"),
        (base + 7200, "LATE", "08:00", "08:30"),
        (base + 10800, "LATEST", "09:00", "09:30"),
    ]
    respx.get(DIRECTIONS_URL).mock(return_value=httpx.Response(200, json=_transit_response(departures)))

    reply = await maps_client.get_train_departures(
        "Bochnia",
        "Kraków Główny",
        count=2,
        arrival_time_iso="2026-07-23T11:00:00+02:00",
    )

    # Should keep the 2 latest (LATE, LATEST), displayed in ascending order,
    # not the 2 earliest (EARLY, MID).
    assert "EARLY" not in reply
    assert "MID" not in reply
    assert reply.index("LATE departs") < reply.index("LATEST departs")
