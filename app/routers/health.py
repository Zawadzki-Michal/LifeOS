from fastapi import APIRouter

from app import ollama_client

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/ollama")
async def health_ollama():
    try:
        models = await ollama_client.list_models()
        return {"status": "ok", "models": models}
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)}
