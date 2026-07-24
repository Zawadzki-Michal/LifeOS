from typing import Awaitable, Callable

import httpx

from app.config import settings


class TerminalToolResult:
    """Wraps a tool result that should become this turn's final reply
    directly, skipping any further local-model round-trips. Used by
    consult_advanced_model (app/tools.py): relaying the cloud model's answer
    back through Qwen for one more round-trip only adds latency (the local
    model, not the cloud call, is consistently the slow part) and risk — a
    real instance of it subtly mistranslating the cloud reply back into
    worse Polish is what prompted this."""

    def __init__(self, content: str):
        self.content = content


async def list_models() -> list[str]:
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(f"{settings.ollama_base_url}/api/tags")
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]


async def generate(model: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["response"]


async def chat(model: str, messages: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["message"]["content"],
            "prompt_tokens": data.get("prompt_eval_count"),
            "completion_tokens": data.get("eval_count"),
        }


async def chat_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    executor: Callable[[str, dict], Awaitable[str | TerminalToolResult]],
    max_iters: int = 6,
) -> dict:
    total_prompt_tokens = 0
    total_completion_tokens = 0
    async with httpx.AsyncClient(timeout=180) as client:
        for _ in range(max_iters):
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={"model": model, "messages": messages, "tools": tools, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            total_prompt_tokens += data.get("prompt_eval_count") or 0
            total_completion_tokens += data.get("eval_count") or 0
            message = data["message"]
            messages.append(message)

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return {
                    "content": message.get("content", ""),
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                }

            terminal: TerminalToolResult | None = None
            for call in tool_calls:
                fn = call["function"]
                result = await executor(fn["name"], fn.get("arguments", {}))
                if isinstance(result, TerminalToolResult):
                    terminal = result
                    messages.append({"role": "tool", "content": result.content})
                else:
                    messages.append({"role": "tool", "content": result})

            if terminal is not None:
                return {
                    "content": terminal.content,
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                }

    return {
        "content": "Sorry, that took too many steps — try rephrasing.",
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
    }
