import datetime as dt
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from app import redis_client
from app.config import settings
from app.db import SessionLocal
from app.models import SavedPlace

TZ = ZoneInfo("Europe/Warsaw")

DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

# The user's known regular commute — lets get_train_departures work with just
# one station name instead of requiring both every time.
DEFAULT_COMMUTE = {
    "bochnia": "Kraków Główny",
    "kraków główny": "Bochnia",
    "krakow glowny": "Bochnia",
    "krakow główny": "Bochnia",
}


def _maps_link(origin: str, destination: str, mode: str = "driving") -> str:
    params = urlencode(
        {"api": "1", "origin": origin, "destination": destination, "travelmode": mode}
    )
    return f"https://www.google.com/maps/dir/?{params}"


def _resolve_place_name(name: str) -> str:
    with SessionLocal() as db:
        place = db.query(SavedPlace).filter(SavedPlace.name.ilike(name.strip())).first()
        return place.address if place else name


async def upsert_saved_place(name: str, address: str) -> str:
    with SessionLocal() as db:
        place = db.query(SavedPlace).filter(SavedPlace.name.ilike(name.strip())).first()
        if place:
            place.address = address
        else:
            db.add(SavedPlace(name=name.strip().lower(), address=address))
        db.commit()
    return f"Saved '{name}' as {address}."


async def _drive(origin: str, destination: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            DIRECTIONS_URL,
            params={
                "origin": origin,
                "destination": destination,
                "mode": "driving",
                "key": settings.google_maps_api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "OK" or not data.get("routes"):
        return f"Couldn't find driving directions to '{destination}' ({data.get('status', 'unknown error')})."

    leg = data["routes"][0]["legs"][0]
    link = _maps_link(origin, destination, "driving")
    return (
        f"Driving to {destination}: {leg['duration']['text']} ({leg['distance']['text']}).\n"
        f"Open in Google Maps: {link}"
    )


async def get_driving_directions(chat_id: int, destination: str) -> str:
    if not settings.google_maps_api_key:
        return "Google Maps API key isn't configured yet, so I can't fetch directions."

    location = await redis_client.get_location(chat_id)
    if location is None:
        return (
            "I don't have your current location on file — share it in Telegram "
            "(attach → Location) and ask again."
        )

    origin = f"{location[0]},{location[1]}"
    destination = _resolve_place_name(destination)
    return await _drive(origin, destination)


async def get_train_departures(
    origin_station: str,
    destination_station: str | None,
    count: int = 4,
    departure_time_iso: str | None = None,
    arrival_time_iso: str | None = None,
) -> str:
    if not settings.google_maps_api_key:
        return "Google Maps API key isn't configured yet, so I can't fetch train times."

    if not destination_station:
        destination_station = DEFAULT_COMMUTE.get(origin_station.strip().lower())
        if not destination_station:
            return (
                "I need a destination station too — I only know the default "
                "Bochnia ↔ Kraków Główny commute pair without one."
            )

    time_params = {}
    if arrival_time_iso:
        arr_dt = dt.datetime.fromisoformat(arrival_time_iso)
        if arr_dt.tzinfo is None:
            arr_dt = arr_dt.replace(tzinfo=TZ)
        time_params["arrival_time"] = int(arr_dt.timestamp())
        when_label = f"arriving by {arr_dt.strftime('%Y-%m-%d %H:%M')}"
    elif departure_time_iso:
        dep_dt = dt.datetime.fromisoformat(departure_time_iso)
        if dep_dt.tzinfo is None:
            dep_dt = dep_dt.replace(tzinfo=TZ)
        time_params["departure_time"] = int(dep_dt.timestamp())
        when_label = f"around {dep_dt.strftime('%Y-%m-%d %H:%M')}"
    else:
        time_params["departure_time"] = "now"
        when_label = "right now"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            DIRECTIONS_URL,
            params={
                "origin": f"{origin_station}, Poland",
                "destination": f"{destination_station}, Poland",
                "mode": "transit",
                "transit_mode": "train",
                "alternatives": "true",
                "key": settings.google_maps_api_key,
                **time_params,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "OK" or not data.get("routes"):
        return (
            f"Couldn't find a train from {origin_station} to {destination_station} "
            f"{when_label} ({data.get('status', 'unknown error')}). Google's "
            "transit data for Polish regional rail is sometimes incomplete — worth "
            "double-checking a PKP/Polregio app."
        )

    departures = []
    seen_departures = set()
    for route in data["routes"]:
        leg = route["legs"][0]
        transit_step = next((s for s in leg["steps"] if s.get("travel_mode") == "TRANSIT"), None)
        if transit_step is None:
            continue
        details = transit_step["transit_details"]
        dep_ts = details["departure_time"]["value"]
        if dep_ts in seen_departures:
            continue
        seen_departures.add(dep_ts)
        line = details["line"].get("short_name") or details["line"].get("name", "train")
        departures.append(
            {
                "ts": dep_ts,
                "line": line,
                "departs": details["departure_time"]["text"],
                "arrives": details["arrival_time"]["text"],
                "duration": leg["duration"]["text"],
            }
        )

    if not departures:
        return f"No direct train found from {origin_station} to {destination_station} {when_label}."

    if arrival_time_iso:
        # Latest departures that still make the deadline are what's actually
        # useful here (maximizes sleep-in/prep time) — not the earliest ones,
        # which could be hours before the target arrival for no reason.
        departures.sort(key=lambda d: d["ts"], reverse=True)
        departures = departures[:count]
        departures.sort(key=lambda d: d["ts"])
    else:
        departures.sort(key=lambda d: d["ts"])
        departures = departures[:count]

    lines = [
        f"- {d['line']} departs {d['departs']}, arrives {d['arrives']} ({d['duration']})"
        for d in departures
    ]
    return f"Trains {when_label} from {origin_station} to {destination_station}:\n" + "\n".join(lines)


async def plan_train_commute() -> str:
    if not settings.google_maps_api_key:
        return "Google Maps API key isn't configured yet, so I can't plan the commute."

    home = _resolve_place_name("home")
    if home == "home":
        return "I don't have your home address saved yet — tell me your home address first."

    drive_summary = await _drive(home, "Bochnia train station, Poland")
    train_summary = await get_train_departures("Bochnia", "Kraków Główny")
    return f"{drive_summary}\n\n{train_summary}"
