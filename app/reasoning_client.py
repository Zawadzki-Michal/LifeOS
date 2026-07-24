"""Cloud hand-off for things local Qwen can't do itself: open-ended
reasoning via consult_advanced_model (app/tools.py), and image analysis via
analyze_image (app/routers/sessions.py's image-messages endpoint) since
Qwen isn't a vision model. Text is redacted before either leaves the box;
an uploaded image itself can't be redacted — an accepted, explicit tradeoff
(see 03-WEBAPP-PLAN.md / this feature's discussion)."""

from app import openrouter_client
from app.config import settings
from app.db import SessionLocal
from app.redaction import redact

SYSTEM_PROMPT = (
    "You are a reasoning assistant helping with an open-ended personal request "
    "(e.g. a meal proposal, health/activity review, or general advice) as part "
    "of a larger personal assistant app. Reply in Polish. Be direct, specific, "
    "and actionable — a few sentences or a short list, not an essay. Some names "
    "may appear as redacted [relation] placeholders (e.g. [wife], [user]) — "
    "just refer to people that way in your reply, don't remark on the redaction."
)

VISION_SYSTEM_PROMPT = (
    "You are analyzing a screenshot for a personal assistant app — typically "
    "Apple Health/Fitness/Watch activity data, a receipt, or similar. Extract "
    "and summarize the concrete numbers/data visible (steps, calories, "
    "workout details, amounts, dates, etc.) clearly and accurately in Polish. "
    "Be concise — a short summary or list, not an essay. If the image doesn't "
    "clearly show what was asked about, say so plainly rather than guessing."
)


async def consult(question: str, context: str | None = None) -> tuple[str, int | None]:
    with SessionLocal() as db:
        redacted_question = redact(question, db)
        redacted_context = redact(context, db) if context else None

    user_content = (
        f"{redacted_context}\n\n{redacted_question}" if redacted_context else redacted_question
    )
    result = await openrouter_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    )
    return result["content"], result.get("completion_tokens")


async def analyze_image(
    image_b64: str, mime_type: str, caption: str | None = None
) -> tuple[str, int | None]:
    """Analyzes an uploaded image (typically an Apple Health/Activity
    screenshot) with a cheap vision model — this is an extraction/OCR-shaped
    task, not one needing frontier reasoning, so it deliberately doesn't use
    the same (pricier) model as consult(). The caption, if any, is redacted
    same as any other text sent to the cloud; the image itself cannot be."""
    with SessionLocal() as db:
        redacted_caption = redact(caption, db) if caption else None

    text_prompt = redacted_caption or "Co pokazuje ten zrzut ekranu? Podsumuj widoczne dane."
    result = await openrouter_client.chat(
        [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                    },
                ],
            },
        ],
        model=settings.openrouter_vision_model,
    )
    return result["content"], result.get("completion_tokens")
