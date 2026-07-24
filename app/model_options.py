"""Single source of truth for the header model-picker's choices — shared by
app/routers/settings.py (validates an incoming key) and app/chat_service.py
(resolves the user's saved choice to an actual model/routing decision).
"local: True" means the choice forces the local Qwen tool-calling path
(app/chat_service.py::run_turn) exactly as if the message had been prefixed
"Local:" (app/routing.py) — without the user needing to type it every time.
"""

from app.config import settings

MODEL_CHOICES: dict[str, dict] = {
    "auto": {"label": "Auto", "slug": None, "local": False},
    "sonnet": {"label": "Sonnet", "slug": settings.openrouter_model, "local": False},
    "gpt": {"label": "GPT-5", "slug": settings.openrouter_gpt_model, "local": False},
    "cheap": {"label": "Cheap (GPT-5 Nano)", "slug": settings.openrouter_cheap_model, "local": False},
    "qwen": {"label": "Qwen (Local)", "slug": None, "local": True},
}

DEFAULT_CHOICE_KEY = "auto"
