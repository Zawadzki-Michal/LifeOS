"""Local speech-to-text via faster-whisper. Fully local, no cloud call —
same reasoning as everything else in this app: voice input/replies can
carry household/health context, so it stays on the box like the LLM does.

The model is multilingual (not the .en-only variant) since conversations
mix English and Polish (place names, train stations). Loads once on first
use and stays cached in memory; that first call is slow (weight download +
load), every call after is fast.
"""

import asyncio
import logging

from faster_whisper import WhisperModel

logger = logging.getLogger("lifeos.speech")

MODEL_SIZE = "small"

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("Loading Whisper model (%s)...", MODEL_SIZE)
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


async def transcribe(audio_path: str) -> str:
    def _run() -> str:
        model = _get_model()
        segments, _ = model.transcribe(audio_path)
        return " ".join(seg.text.strip() for seg in segments).strip()

    return await asyncio.to_thread(_run)
