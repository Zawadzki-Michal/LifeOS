import base64
import datetime as dt
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app import chat_service, chat_store, reasoning_client, redis_client, speech
from app.auth import require_auth
from app.config import settings
from app.db import SessionLocal
from app.models import InteractionLog

router = APIRouter(prefix="/api/sessions", dependencies=[Depends(require_auth)])

TITLE_PREVIEW_LEN = 60


async def _json_body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _session_dict(session) -> dict:
    return {
        "id": session.id,
        "title": session.title,
        "channel": session.channel,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "archived": session.archived,
        "is_scheduler": session.is_scheduler,
    }


def _message_dict(message) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "model": message.model,
    }


@router.get("")
def list_sessions(include_archived: bool = False):
    sessions = chat_store.list_sessions("web", include_archived=include_archived)
    return [_session_dict(s) for s in sessions]


@router.post("")
async def create_session(request: Request):
    body = await _json_body(request)
    session = chat_store.create_session("web", title=body.get("title"))
    return _session_dict(session)


@router.patch("/{session_id}")
async def update_session(session_id: int, request: Request):
    if chat_store.get_session(session_id, channel="web") is None:
        raise HTTPException(status_code=404, detail="Session not found")
    body = await _json_body(request)
    session = chat_store.update_session(
        session_id, title=body.get("title"), archived=body.get("archived")
    )
    return _session_dict(session)


@router.delete("/{session_id}")
def delete_session(session_id: int):
    if chat_store.get_session(session_id, channel="web") is None:
        raise HTTPException(status_code=404, detail="Session not found")
    chat_store.delete_session(session_id)
    return {"ok": True}


@router.get("/{session_id}/messages")
def list_messages(session_id: int):
    if chat_store.get_session(session_id, channel="web") is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return [_message_dict(m) for m in chat_store.list_all_messages(session_id)]


def _get_web_session_or_404(session_id: int):
    session = chat_store.get_session(session_id, channel="web")
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _send_text(session_id: int, session, text: str, terse: bool = False) -> str:
    if session.title is None:
        preview = text if len(text) <= TITLE_PREVIEW_LEN else text[: TITLE_PREVIEW_LEN - 1] + "…"
        chat_store.update_session(session_id, title=preview)
    return await chat_service.run_turn(session_id, session_id, "web", text, terse=terse)


@router.post("/{session_id}/messages")
async def send_message(session_id: int, request: Request):
    session = _get_web_session_or_404(session_id)

    body = await _json_body(request)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    reply = await _send_text(session_id, session, text)
    return {"reply": reply}


@router.post("/{session_id}/voice-messages")
async def send_voice_message(session_id: int, file: UploadFile = File(...)):
    session = _get_web_session_or_404(session_id)

    try:
        await redis_client.publish_status_event(session_id, "transcribing")
    except Exception:
        pass

    with tempfile.NamedTemporaryFile(suffix=".audio") as tmp:
        tmp.write(await file.read())
        tmp.flush()
        transcript = await speech.transcribe(tmp.name)

    if not transcript:
        raise HTTPException(status_code=400, detail="Couldn't make out any speech in that recording")

    reply = await _send_text(session_id, session, transcript, terse=True)
    return {"transcript": transcript, "reply": reply}


@router.post("/{session_id}/image-messages")
async def send_image_message(
    session_id: int, file: UploadFile = File(...), caption: str | None = Form(None)
):
    """Images can't go through the normal local-Qwen tool-calling path — the
    local model isn't vision-capable — so this hands off to a cheap vision
    model (settings.openrouter_vision_model) directly. The caption is
    redacted like any other outbound text; the image itself cannot be —
    an explicit, accepted tradeoff (see conversation/03-WEBAPP-PLAN.md)."""
    session = _get_web_session_or_404(session_id)

    try:
        await redis_client.publish_status_event(session_id, "analyzing_image")
    except Exception:
        pass

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload")

    mime_type = file.content_type or "image/jpeg"
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    caption = (caption or "").strip() or None

    reply, tokens = await reasoning_client.analyze_image(image_b64, mime_type, caption)

    user_content = f"📷 {caption}" if caption else "📷 [obraz]"
    if session.title is None:
        preview = (
            user_content
            if len(user_content) <= TITLE_PREVIEW_LEN
            else user_content[: TITLE_PREVIEW_LEN - 1] + "…"
        )
        chat_store.update_session(session_id, title=preview)

    chat_store.append_message(session_id, "user", user_content)
    chat_store.append_message(
        session_id, "assistant", reply, tokens=tokens, model=settings.openrouter_vision_model
    )

    with SessionLocal() as db:
        db.add(
            InteractionLog(
                ts=dt.datetime.now(dt.timezone.utc),
                direction="out",
                channel="web",
                agent="vision",
                tokens_local=None,
                tokens_cloud=tokens,
                redaction_applied="yes (caption only — image not redactable)",
            )
        )
        db.commit()

    return {"reply": reply}
