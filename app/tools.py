"""Tool definitions exposed to the local model via Ollama's tool-calling."""

from app import calendar_client, maps_client

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_driving_directions",
            "description": (
                "Get driving time and distance from the user's last shared Telegram "
                "location to a destination, plus a clickable Google Maps link. "
                "Destination can be a saved place name (e.g. 'mom', 'home', 'work') "
                "or a raw address."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "Destination address or saved place name.",
                    }
                },
                "required": ["destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_train_departures",
            "description": (
                "Get the next several upcoming train departures (default 4) between "
                "two Polish train stations, e.g. Bochnia and Kraków Główny."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_station": {
                        "type": "string",
                        "description": "Departure station name.",
                    },
                    "destination_station": {
                        "type": "string",
                        "description": (
                            "Arrival station name. Optional if origin_station is "
                            "Bochnia or Kraków Główny — defaults to the other."
                        ),
                    },
                    "count": {
                        "type": "integer",
                        "description": "How many upcoming departures to return. Defaults to 4.",
                    },
                },
                "required": ["origin_station"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_train_commute",
            "description": (
                "Use when the user says they're heading to work by train soon (or "
                "asks about their train commute) without naming stations. Combines "
                "driving time from their saved home address to Bochnia station with "
                "the next train from Bochnia to Kraków Główny. Takes no arguments."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_saved_place",
            "description": (
                "Save or update a named place's address (e.g. 'home', 'mom', 'work') "
                "so future directions requests can use the name instead of the full "
                "address. Use this whenever the user tells you an address to remember."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short label, e.g. 'mom' or 'work'.",
                    },
                    "address": {
                        "type": "string",
                        "description": "Full address.",
                    },
                },
                "required": ["name", "address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": (
                "List upcoming Google Calendar events, including each event's id "
                "(needed to later update or delete it)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to look. Defaults to 7.",
                    },
                    "calendar": {
                        "type": "string",
                        "description": "'primary' (default) or 'family'.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Create a new Google Calendar event. Resolve relative dates/times "
                "(e.g. 'Wednesday', 'tomorrow') to an actual ISO 8601 datetime "
                "yourself using the current date/time given in your instructions "
                "before calling this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start_iso": {
                        "type": "string",
                        "description": "Start time, ISO 8601, e.g. 2026-07-22T07:00:00.",
                    },
                    "end_iso": {
                        "type": "string",
                        "description": "End time, ISO 8601. Defaults to 1 hour after start.",
                    },
                    "calendar": {
                        "type": "string",
                        "description": "'primary' (default) or 'family'.",
                    },
                    "location": {"type": "string", "description": "Optional location."},
                },
                "required": ["title", "start_iso"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": (
                "Update an existing Google Calendar event. Call list_calendar_events "
                "first to find the event's id if you don't already have it from this "
                "conversation. Only include the fields that should change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event's id."},
                    "calendar": {
                        "type": "string",
                        "description": "'primary' (default) or 'family' — must match where the event lives.",
                    },
                    "title": {"type": "string", "description": "New title, if changing."},
                    "start_iso": {
                        "type": "string",
                        "description": "New start time, ISO 8601, if changing.",
                    },
                    "end_iso": {
                        "type": "string",
                        "description": "New end time, ISO 8601, if changing.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": (
                "Delete/cancel a Google Calendar event. Call list_calendar_events "
                "first to find the event's id if you don't already have it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event's id."},
                    "calendar": {
                        "type": "string",
                        "description": "'primary' (default) or 'family' — must match where the event lives.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
]


def make_executor(chat_id: int):
    async def execute(name: str, args: dict) -> str:
        if name == "get_driving_directions":
            return await maps_client.get_driving_directions(chat_id, args["destination"])
        if name == "get_train_departures":
            return await maps_client.get_train_departures(
                args["origin_station"],
                args.get("destination_station"),
                args.get("count", 4),
            )
        if name == "plan_train_commute":
            return await maps_client.plan_train_commute()
        if name == "update_saved_place":
            return await maps_client.upsert_saved_place(args["name"], args["address"])
        if name == "list_calendar_events":
            return await calendar_client.list_upcoming_events(
                args.get("days_ahead", 7), args.get("calendar", "primary")
            )
        if name == "create_calendar_event":
            return await calendar_client.create_event(
                args["title"],
                args["start_iso"],
                args.get("end_iso"),
                args.get("calendar", "primary"),
                args.get("location"),
            )
        if name == "update_calendar_event":
            return await calendar_client.update_event(
                args["event_id"],
                args.get("calendar", "primary"),
                args.get("title"),
                args.get("start_iso"),
                args.get("end_iso"),
            )
        if name == "delete_calendar_event":
            return await calendar_client.delete_event(
                args["event_id"], args.get("calendar", "primary")
            )
        return f"Unknown tool: {name}"

    return execute
