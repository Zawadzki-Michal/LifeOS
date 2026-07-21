import datetime as dt

import httpx

from app import redis_client
from app.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


def _configured() -> bool:
    return bool(
        settings.google_calendar_client_id
        and settings.google_calendar_client_secret
        and settings.google_calendar_refresh_token
    )


async def _get_access_token() -> str:
    cached = await redis_client.get_cached_access_token()
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.google_calendar_client_id,
                "client_secret": settings.google_calendar_client_secret,
                "refresh_token": settings.google_calendar_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]

    await redis_client.set_cached_access_token(token)
    return token


async def _resolve_calendar_id(name: str) -> str:
    name = (name or "primary").strip().lower()
    if name in ("primary", ""):
        return "primary"

    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{CALENDAR_API_BASE}/users/me/calendarList",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        for cal in resp.json().get("items", []):
            if cal.get("summary", "").strip().lower() == name:
                return cal["id"]
    return "primary"


async def list_upcoming_events(days_ahead: int = 7, calendar: str = "primary") -> str:
    if not _configured():
        return "Google Calendar isn't connected yet."

    cal_id = await _resolve_calendar_id(calendar)
    token = await _get_access_token()
    now = dt.datetime.now(dt.timezone.utc)
    time_max = now + dt.timedelta(days=days_ahead)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{CALENDAR_API_BASE}/calendars/{cal_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "timeMin": now.isoformat(),
                "timeMax": time_max.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                # Without this, Google formats dateTime using the calendar's own
                # default timezone (not the event's), which can silently show the
                # wrong wall-clock hour when they differ.
                "timeZone": "Europe/Warsaw",
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

    if not items:
        return f"No events in the next {days_ahead} days on the {calendar} calendar."

    lines = []
    for ev in items:
        start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date"))
        title = ev.get("summary", "(no title)")
        lines.append(f"- [{ev['id']}] {title} — {start}")
    return "Upcoming events:\n" + "\n".join(lines)


async def create_event(
    title: str,
    start_iso: str,
    end_iso: str | None = None,
    calendar: str = "primary",
    location: str | None = None,
) -> str:
    if not _configured():
        return "Google Calendar isn't connected yet."

    if not end_iso:
        start_dt = dt.datetime.fromisoformat(start_iso)
        end_iso = (start_dt + dt.timedelta(hours=1)).isoformat()

    cal_id = await _resolve_calendar_id(calendar)
    token = await _get_access_token()
    body = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": "Europe/Warsaw"},
        "end": {"dateTime": end_iso, "timeZone": "Europe/Warsaw"},
    }
    if location:
        body["location"] = location

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{CALENDAR_API_BASE}/calendars/{cal_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        resp.raise_for_status()
        ev = resp.json()

    # Google's insert response echoes dateTime formatted using the calendar's
    # default timezone rather than the event's, which can show a misleading
    # wall-clock hour — use the values we actually sent (known correct) instead.
    return (
        f"Created '{title}' on the {calendar} calendar: "
        f"{start_iso} to {end_iso} (id: {ev['id']})."
    )


async def update_event(
    event_id: str,
    calendar: str = "primary",
    title: str | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
) -> str:
    if not _configured():
        return "Google Calendar isn't connected yet."

    body: dict = {}
    if title:
        body["summary"] = title
    if start_iso:
        body["start"] = {"dateTime": start_iso, "timeZone": "Europe/Warsaw"}
    if end_iso:
        body["end"] = {"dateTime": end_iso, "timeZone": "Europe/Warsaw"}
    if not body:
        return "Nothing to update."

    cal_id = await _resolve_calendar_id(calendar)
    token = await _get_access_token()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.patch(
            f"{CALENDAR_API_BASE}/calendars/{cal_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        if resp.status_code == 404:
            return f"No event found with id {event_id} on the {calendar} calendar."
        resp.raise_for_status()

    # Same timezone-formatting caveat as create_event — report what we sent,
    # not Google's echoed response.
    changes = []
    if title:
        changes.append(f"title -> '{title}'")
    if start_iso:
        changes.append(f"start -> {start_iso}")
    if end_iso:
        changes.append(f"end -> {end_iso}")
    return f"Updated event {event_id}: " + ", ".join(changes) + "."


async def delete_event(event_id: str, calendar: str = "primary") -> str:
    if not _configured():
        return "Google Calendar isn't connected yet."

    cal_id = await _resolve_calendar_id(calendar)
    token = await _get_access_token()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.delete(
            f"{CALENDAR_API_BASE}/calendars/{cal_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 404:
            return f"No event found with id {event_id} on the {calendar} calendar."
        resp.raise_for_status()

    return "Event deleted."
