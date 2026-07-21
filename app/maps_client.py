from urllib.parse import urlencode

import httpx

from app import redis_client
from app.config import settings
from app.db import SessionLocal
from app.models import SavedPlace

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


async def get_train_departures(origin_station: str, destination_station: str | None) -> str:
    if not settings.google_maps_api_key:
        return "Google Maps API key isn't configured yet, so I can't fetch train times."

    if not destination_station:
        destination_station = DEFAULT_COMMUTE.get(origin_station.strip().lower())
        if not destination_station:
            return (
                "I need a destination station too — I only know the default "
                "Bochnia ↔ Kraków Główny commute pair without one."
            )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            DIRECTIONS_URL,
            params={
                "origin": f"{origin_station}, Poland",
                "destination": f"{destination_station}, Poland",
                "mode": "transit",
                "transit_mode": "train",
                "departure_time": "now",
                "key": settings.google_maps_api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "OK" or not data.get("routes"):
        return (
            f"Couldn't find a train from {origin_station} to {destination_station} "
            f"({data.get('status', 'unknown error')}). Google's transit data for Polish "
            "regional rail is sometimes incomplete — worth double-checking a PKP/Polregio app."
        )

    leg = data["routes"][0]["legs"][0]
    transit_step = next((s for s in leg["steps"] if s.get("travel_mode") == "TRANSIT"), None)
    if transit_step is None:
        return f"No direct train found from {origin_station} to {destination_station} right now."

    details = transit_step["transit_details"]
    line = details["line"].get("short_name") or details["line"].get("name", "train")
    return (
        f"Next {line} from {origin_station} to {destination_station}: "
        f"departs {details['departure_time']['text']}, "
        f"arrives {details['arrival_time']['text']} ({leg['duration']['text']})."
    )


async def plan_train_commute() -> str:
    if not settings.google_maps_api_key:
        return "Google Maps API key isn't configured yet, so I can't plan the commute."

    home = _resolve_place_name("home")
    if home == "home":
        return "I don't have your home address saved yet — tell me your home address first."

    drive_summary = await _drive(home, "Bochnia train station, Poland")
    train_summary = await get_train_departures("Bochnia", "Kraków Główny")
    return f"{drive_summary}\n\n{train_summary}"
