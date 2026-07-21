"""Tool definitions exposed to the local model via Ollama's tool-calling."""

from app import maps_client

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_driving_directions",
            "description": (
                "Get driving time and distance from the user's last shared Telegram "
                "location to a destination, plus a clickable Google Maps link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "Destination address or place name.",
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
                "Get the next train departure and arrival time between two Polish "
                "train stations, e.g. Bochnia and Kraków Główny."
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
                },
                "required": ["origin_station"],
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
                args["origin_station"], args.get("destination_station")
            )
        return f"Unknown tool: {name}"

    return execute
