"""Tool definitions exposed to the local model via Ollama's tool-calling."""

import logging

from app import (
    calendar_client,
    finance_client,
    health_client,
    maps_client,
    nutrition_client,
    reasoning_client,
    redis_client,
)
from app.ollama_client import TerminalToolResult

logger = logging.getLogger("lifeos.tools")

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
                "Get train departures between two Polish stations, e.g. Bochnia and "
                "Kraków Główny. Defaults to departures from right now. Can also look up "
                "trains departing around a specific future time ('trains tomorrow "
                "around 3pm'), or — for 'what time do I need to leave to be there by "
                "X' questions like getting to the office by 9am — trains arriving by a "
                "specific time instead, which is the one that actually answers that "
                "kind of question correctly."
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
                    "departure_time_iso": {
                        "type": "string",
                        "description": (
                            "Optional. Resolve a relative time like 'tomorrow around "
                            "3pm' into an actual ISO 8601 datetime yourself (same as "
                            "calendar events) using the current date/time given in "
                            "your instructions. Omit entirely for 'right now'. Don't "
                            "combine with arrival_time_iso — pick whichever matches "
                            "the question."
                        ),
                    },
                    "arrival_time_iso": {
                        "type": "string",
                        "description": (
                            "Optional. Use this instead of departure_time_iso for "
                            "'I need to be there by X' questions (e.g. an office event "
                            "at 9am) — resolve the target arrival time into ISO 8601 "
                            "yourself, same as calendar events, and this returns trains "
                            "that get there by then."
                        ),
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
    {
        "type": "function",
        "function": {
            "name": "log_expense",
            "description": (
                "Log a new expense. If the category doesn't exist yet it's created "
                "automatically — categories aren't fixed, use whatever name fits "
                "(e.g. 'groceries', 'fuel', 'subscriptions')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_pln": {"type": "number", "description": "Amount in PLN."},
                    "category": {
                        "type": "string",
                        "description": "Category name, e.g. 'groceries', 'fuel', 'kids'.",
                    },
                    "merchant": {"type": "string", "description": "Optional merchant/store name."},
                    "note": {"type": "string", "description": "Optional free-text note."},
                    "raw_text": {
                        "type": "string",
                        "description": "The user's original message, for record-keeping.",
                    },
                },
                "required": ["amount_pln", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_expense_category",
            "description": (
                "Explicitly create a new expense category (optionally with a monthly "
                "budget in PLN), or set/update the budget on an existing one. Not "
                "required before logging an expense — log_expense auto-creates "
                "categories — use this when the user specifically wants to define a "
                "category or set a budget for it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Category name."},
                    "monthly_budget": {
                        "type": "number",
                        "description": "Optional monthly budget in PLN for this category.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": (
                "Get total spending for a period, broken down by category, e.g. "
                "'how much have I spent this month' or 'how much on groceries this "
                "week'. If a category is given, returns just that category's total. "
                "Month totals also show progress against any category budgets set."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "'today', 'week', or 'month' (default 'month').",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category to filter to, e.g. 'groceries'.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_bills",
            "description": "List upcoming recurring bills and their due dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to look. Defaults to 30.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_bill",
            "description": (
                "Add a new recurring bill (e.g. rent, mortgage, insurance, subscription). "
                "It is automatically posted as an expense each cycle once its due date "
                "arrives, and its due date rolls forward on its own — the user only "
                "needs to describe it once, never re-log it manually each month."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Bill name, e.g. 'Mortgage'."},
                    "amount_pln": {"type": "number", "description": "Amount in PLN."},
                    "due_day": {
                        "type": "integer",
                        "description": "Day of the month it's due (1-31).",
                    },
                    "recurrence": {
                        "type": "string",
                        "description": "'monthly' (default) or 'yearly'.",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Expense category this bill's cost should count towards, "
                            "e.g. 'mortgage', 'subscriptions', 'insurance'. Prefer an "
                            "existing category (see the list in your instructions) — "
                            "e.g. all streaming/cloud/software subscriptions should "
                            "share the 'subscriptions' category, not one each."
                        ),
                    },
                    "amount_is_fixed": {
                        "type": "boolean",
                        "description": (
                            "False if the amount varies each cycle (e.g. a utility "
                            "bill) — it then won't auto-post; the user will be asked "
                            "to confirm the actual amount via log_bill_payment when "
                            "it's due. Defaults to true (fixed amount, e.g. rent, "
                            "mortgage, subscriptions)."
                        ),
                    },
                },
                "required": ["name", "amount_pln", "due_day", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_bill",
            "description": (
                "Update an existing recurring bill's amount, due day, recurrence, "
                "category, or whether its amount is fixed. Only include fields that "
                "should change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The bill's current name."},
                    "new_name": {"type": "string", "description": "New name, if renaming."},
                    "amount_pln": {"type": "number", "description": "New amount in PLN, if changing."},
                    "due_day": {
                        "type": "integer",
                        "description": "New due day of the month, if changing.",
                    },
                    "recurrence": {
                        "type": "string",
                        "description": "New recurrence ('monthly' or 'yearly'), if changing.",
                    },
                    "category": {"type": "string", "description": "New category, if changing."},
                    "amount_is_fixed": {
                        "type": "boolean",
                        "description": "New fixed/variable flag, if changing.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_bill_payment",
            "description": (
                "Confirm the actual paid amount for a bill that's due — required for "
                "variable-amount bills (they won't auto-post), and also usable to "
                "override a fixed bill's amount for a single cycle. Logs the expense "
                "and advances the bill's due date to the next cycle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The bill's name."},
                    "amount_pln": {"type": "number", "description": "Actual amount paid, in PLN."},
                },
                "required": ["name", "amount_pln"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fixed_monthly_overhead",
            "description": (
                "Total committed recurring cost per month across all bills (yearly "
                "bills counted as amount/12) — what's locked in before any "
                "discretionary spending. Use for questions like 'what are my fixed "
                "monthly costs' or 'how much is committed before I can save anything'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_expenses",
            "description": (
                "List individual recent expenses (with their id, needed to delete one) "
                "— use this before delete_expense to find the right id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of expenses to return. Defaults to 10.",
                    },
                    "category": {"type": "string", "description": "Optional category filter."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_expense",
            "description": (
                "Delete a single logged expense by id. Call list_recent_expenses first "
                "if you don't already have the id from this conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expense_id": {"type": "integer", "description": "The expense's id."}
                },
                "required": ["expense_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_bill",
            "description": (
                "Delete a recurring bill by name or id so it stops auto-posting as an "
                "expense each cycle. Does not remove expenses it already posted. If "
                "multiple bills share a name you'll be given ids to pick from — call "
                "again with bill_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The bill's name."},
                    "bill_id": {
                        "type": "integer",
                        "description": "The bill's id, if known (e.g. after a disambiguation prompt).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_health_summary",
            "description": (
                "Get an Apple Health/Fitness summary for a period — steps, active "
                "energy burned, sleep, resting heart rate, and workouts. Use for "
                "questions like 'how did I sleep this week' or 'how active was I "
                "today'. Data only exists from whenever Apple Health sync was set up."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "'today', 'week', or 'month' (default 'week').",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_meal",
            "description": (
                "Log a meal the user describes. Estimate the calories and macros "
                "yourself from the description (same way you'd reason about it if "
                "asked directly) — there is no external nutrition lookup, your "
                "estimate is what gets stored."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What was eaten, in the user's words."},
                    "est_kcal": {"type": "integer", "description": "Your estimated calories for this meal."},
                    "est_protein_g": {"type": "integer", "description": "Estimated protein in grams."},
                    "est_carbs_g": {"type": "integer", "description": "Estimated carbs in grams."},
                    "est_fat_g": {"type": "integer", "description": "Estimated fat in grams."},
                    "meal_type": {
                        "type": "string",
                        "description": "'breakfast', 'lunch', 'dinner', or 'snack', if apparent.",
                    },
                },
                "required": ["description", "est_kcal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_nutrition",
            "description": (
                "Get calories/protein logged so far today (or another date) against "
                "the day's target, including how much budget remains. Use this before "
                "proposing a meal so the proposal fits the user's remaining calories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_iso": {
                        "type": "string",
                        "description": "Optional date (YYYY-MM-DD). Defaults to today.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_daily_target",
            "description": "Set the user's calorie target for a day (defaults to today).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kcal": {"type": "integer", "description": "Daily calorie target."},
                    "date_iso": {
                        "type": "string",
                        "description": "Optional date (YYYY-MM-DD). Defaults to today.",
                    },
                },
                "required": ["kcal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consult_advanced_model",
            "description": (
                "Hand off to a more capable cloud model for open-ended requests that "
                "need real synthesis, planning, or advice rather than a data lookup or "
                "action — e.g. 'what should I cook with chicken, rice, and broccoli, "
                "I have about 600kcal left today', 'review my activity and weight this "
                "week and give me advice', or any other 'what should I do about X' "
                "question. Do NOT use this for straightforward data operations you "
                "already have a tool for (logging/querying expenses, calendar, meals, "
                "health data) — handle those yourself directly without this tool. "
                "Gather any relevant numbers first via your other tools (e.g. "
                "get_daily_nutrition for remaining calories, get_health_summary for "
                "activity/sleep, or the latest weight) and pass them in `context` so "
                "the answer is grounded in real data instead of guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The user's open-ended question or request, restated clearly.",
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "Relevant data you already gathered from other tools this "
                            "turn (e.g. remaining calorie budget, recent workouts, "
                            "latest weight) to ground the answer in real numbers."
                        ),
                    },
                },
                "required": ["question"],
            },
        },
    },
]


def make_executor(chat_id: int, usage: dict | None = None, status_session_id: int | None = None):
    """`usage`, if given, is a mutable dict the executor records activity
    into: cloud_used/cloud_tokens (read by chat_service.py to populate
    InteractionLog), and tool_calls — every tool actually invoked this turn
    (name + args), a real audit trail persisted to chat_message.tool_calls_json.
    Added after a live incident where the local model described creating
    five calendar events it never actually called the tool for — this makes
    "did it really do that" a lookup instead of a manual calendar-API check.
    `status_session_id`, if given, gets a "thinking_cloud" live status ping
    (app.redis_client) right before the OpenRouter call, so the webapp UI can
    show it's not just the slow local model still working."""

    async def _dispatch(name: str, args: dict) -> str:
        if name == "get_driving_directions":
            return await maps_client.get_driving_directions(chat_id, args["destination"])
        if name == "get_train_departures":
            return await maps_client.get_train_departures(
                args["origin_station"],
                args.get("destination_station"),
                args.get("count", 4),
                args.get("departure_time_iso"),
                args.get("arrival_time_iso"),
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
        if name == "log_expense":
            return await finance_client.log_expense(
                args["amount_pln"],
                args["category"],
                args.get("merchant"),
                args.get("note"),
                args.get("raw_text"),
            )
        if name == "add_expense_category":
            return await finance_client.add_expense_category(
                args["name"], args.get("monthly_budget")
            )
        if name == "get_spending_summary":
            return await finance_client.get_spending_summary(
                args.get("period", "month"), args.get("category")
            )
        if name == "list_bills":
            return await finance_client.list_bills(args.get("days_ahead", 30))
        if name == "add_bill":
            return await finance_client.add_bill(
                args["name"],
                args["amount_pln"],
                args["due_day"],
                args["category"],
                args.get("recurrence", "monthly"),
                args.get("amount_is_fixed", True),
            )
        if name == "update_bill":
            return await finance_client.update_bill(
                args["name"],
                args.get("new_name"),
                args.get("amount_pln"),
                args.get("due_day"),
                args.get("recurrence"),
                args.get("category"),
                args.get("amount_is_fixed"),
            )
        if name == "log_bill_payment":
            return await finance_client.log_bill_payment(args["name"], args["amount_pln"])
        if name == "get_fixed_monthly_overhead":
            return await finance_client.get_fixed_monthly_overhead()
        if name == "list_recent_expenses":
            return await finance_client.list_recent_expenses(
                args.get("limit", 10), args.get("category")
            )
        if name == "delete_expense":
            return await finance_client.delete_expense(args["expense_id"])
        if name == "delete_bill":
            return await finance_client.delete_bill(args.get("name"), args.get("bill_id"))
        if name == "get_health_summary":
            return await health_client.get_health_summary(args.get("period", "week"))
        if name == "log_meal":
            return await nutrition_client.log_meal(
                args["description"],
                args["est_kcal"],
                args.get("est_protein_g"),
                args.get("est_carbs_g"),
                args.get("est_fat_g"),
                args.get("meal_type"),
            )
        if name == "get_daily_nutrition":
            return await nutrition_client.get_daily_nutrition(args.get("date_iso"))
        if name == "set_daily_target":
            return await nutrition_client.set_daily_target(args["kcal"], args.get("date_iso"))
        if name == "consult_advanced_model":
            if status_session_id is not None:
                try:
                    await redis_client.publish_status_event(status_session_id, "thinking_cloud")
                except Exception:
                    logger.exception("Failed to publish live status event")
            reply, tokens = await reasoning_client.consult(args["question"], args.get("context"))
            if usage is not None:
                usage["cloud_used"] = True
                usage["cloud_tokens"] = (usage.get("cloud_tokens") or 0) + (tokens or 0)
            # Terminal: return the cloud model's answer directly as this
            # turn's final reply rather than looping back to Qwen to relay
            # it — that extra round-trip was consistently the slowest step
            # and risked altering (once, mistranslating) the cloud answer.
            return TerminalToolResult(reply)
        return f"Unknown tool: {name}"

    async def execute(name: str, args: dict) -> str:
        result = await _dispatch(name, args)
        if usage is not None:
            usage.setdefault("tool_calls", []).append({"name": name, "args": args})
        return result

    return execute
