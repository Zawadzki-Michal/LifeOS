"""reasoning_client.consult is the only path through which text reaches
OpenRouter — this pins down that redaction always runs first, on both the
question and the context, before anything is sent out."""

from unittest.mock import AsyncMock

from app import reasoning_client
from app.db import SessionLocal
from app.models import HouseholdMember


async def test_consult_redacts_question_and_context_before_sending(monkeypatch):
    with SessionLocal() as db:
        db.add(HouseholdMember(relation="wife", name="Ania"))
        db.commit()

    mock_chat = AsyncMock(
        return_value={"content": "advice here", "completion_tokens": 42}
    )
    monkeypatch.setattr(reasoning_client.openrouter_client, "chat", mock_chat)

    reply, tokens = await reasoning_client.consult(
        "Should Ania and I go for a run?", context="Ania ran 5k yesterday."
    )

    assert reply == "advice here"
    assert tokens == 42
    sent_messages = mock_chat.await_args.args[0]
    user_message = sent_messages[-1]["content"]
    assert "Ania" not in user_message
    assert "[wife]" in user_message


async def test_consult_without_context_sends_question_only(monkeypatch):
    mock_chat = AsyncMock(return_value={"content": "ok", "completion_tokens": 5})
    monkeypatch.setattr(reasoning_client.openrouter_client, "chat", mock_chat)

    await reasoning_client.consult("What should I eat?")

    sent_messages = mock_chat.await_args.args[0]
    assert sent_messages[-1]["content"] == "What should I eat?"


async def test_analyze_image_uses_the_cheaper_vision_model(monkeypatch):
    mock_chat = AsyncMock(return_value={"content": "steps: 8000", "completion_tokens": 12})
    monkeypatch.setattr(reasoning_client.openrouter_client, "chat", mock_chat)

    await reasoning_client.analyze_image("base64data", "image/png", "how many steps today?")

    assert mock_chat.await_args.kwargs["model"] == reasoning_client.settings.openrouter_vision_model
    assert mock_chat.await_args.kwargs["model"] != reasoning_client.settings.openrouter_model


async def test_analyze_image_redacts_caption_but_not_the_image_bytes(monkeypatch):
    with SessionLocal() as db:
        db.add(HouseholdMember(relation="wife", name="Ania"))
        db.commit()

    mock_chat = AsyncMock(return_value={"content": "ok", "completion_tokens": 5})
    monkeypatch.setattr(reasoning_client.openrouter_client, "chat", mock_chat)

    await reasoning_client.analyze_image("unredactable-base64-bytes", "image/png", "Ania's steps today")

    sent_messages = mock_chat.await_args.args[0]
    content_blocks = sent_messages[-1]["content"]
    text_block = next(b for b in content_blocks if b["type"] == "text")
    image_block = next(b for b in content_blocks if b["type"] == "image_url")

    assert "Ania" not in text_block["text"]
    assert "[wife]" in text_block["text"]
    assert "unredactable-base64-bytes" in image_block["image_url"]["url"]


async def test_analyze_image_without_caption_uses_a_default_prompt(monkeypatch):
    mock_chat = AsyncMock(return_value={"content": "ok", "completion_tokens": 5})
    monkeypatch.setattr(reasoning_client.openrouter_client, "chat", mock_chat)

    await reasoning_client.analyze_image("base64data", "image/jpeg", None)

    sent_messages = mock_chat.await_args.args[0]
    text_block = next(b for b in sent_messages[-1]["content"] if b["type"] == "text")
    assert text_block["text"]  # some default prompt, not empty


async def test_analyze_image_embeds_correct_mime_type_in_data_url(monkeypatch):
    mock_chat = AsyncMock(return_value={"content": "ok", "completion_tokens": 5})
    monkeypatch.setattr(reasoning_client.openrouter_client, "chat", mock_chat)

    await reasoning_client.analyze_image("xyz", "image/webp", "caption")

    sent_messages = mock_chat.await_args.args[0]
    image_block = next(b for b in sent_messages[-1]["content"] if b["type"] == "image_url")
    assert image_block["image_url"]["url"] == "data:image/webp;base64,xyz"
