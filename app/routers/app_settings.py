"""User-adjustable app settings — currently just the header model picker.
Single-tenant: reads/writes the one User row, same pattern as
app/redaction.py / app/prompts.py (db.query(User).first())."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import require_auth
from app.db import SessionLocal
from app.model_options import DEFAULT_CHOICE_KEY, MODEL_CHOICES
from app.models import User

router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_auth)])


async def _json_body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _options() -> list[dict]:
    return [{"key": key, "label": choice["label"]} for key, choice in MODEL_CHOICES.items()]


@router.get("")
async def get_settings():
    with SessionLocal() as db:
        user = db.query(User).first()
        default_model = (user.default_chat_model if user else None) or DEFAULT_CHOICE_KEY
    return {"default_model": default_model, "options": _options()}


@router.patch("")
async def update_settings(request: Request):
    body = await _json_body(request)
    default_model = body.get("default_model")
    if default_model not in MODEL_CHOICES:
        raise HTTPException(status_code=400, detail=f"Unknown model choice: {default_model!r}")

    with SessionLocal() as db:
        user = db.query(User).first()
        if user is None:
            raise HTTPException(status_code=404, detail="No user configured")
        user.default_chat_model = default_model
        db.commit()

    return {"default_model": default_model, "options": _options()}
