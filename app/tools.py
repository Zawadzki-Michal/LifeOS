"""Tool definitions exposed to the local model via Ollama's tool-calling."""

from app import maps_client

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
        return f"Unknown tool: {name}"

    return execute
