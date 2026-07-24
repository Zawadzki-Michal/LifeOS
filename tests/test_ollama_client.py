"""ollama_client.chat_with_tools's tool-calling loop — respx mocks Ollama's
HTTP API (same pattern as calendar_client/maps_client tests). TerminalToolResult
is the short-circuit consult_advanced_model (app/tools.py) uses to skip a
final local-model relay round-trip: that extra round-trip was consistently
the slowest step in a turn and, once, subtly mistranslated a cloud reply back
into worse Polish — returning the cloud answer directly avoids both.
"""

import httpx
import respx

from app import ollama_client
from app.config import settings
from app.ollama_client import TerminalToolResult

CHAT_URL = f"{settings.ollama_base_url}/api/chat"


@respx.mock
async def test_chat_with_tools_returns_content_directly_when_no_tool_calls():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hi there"},
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )
    )

    async def executor(name, args):
        raise AssertionError("no tool should be called")

    result = await ollama_client.chat_with_tools(
        "qwen", [{"role": "user", "content": "hi"}], [], executor
    )

    assert result == {"content": "hi there", "prompt_tokens": 10, "completion_tokens": 5}


@respx.mock
async def test_chat_with_tools_loops_after_a_normal_tool_result():
    route = respx.post(CHAT_URL)
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "get_x", "arguments": {}}}],
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        ),
        httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "final answer"},
                "prompt_eval_count": 20,
                "eval_count": 8,
            },
        ),
    ]

    async def executor(name, args):
        assert name == "get_x"
        return "tool result text"

    result = await ollama_client.chat_with_tools(
        "qwen", [{"role": "user", "content": "hi"}], [], executor
    )

    assert result == {"content": "final answer", "prompt_tokens": 30, "completion_tokens": 13}
    assert route.call_count == 2


@respx.mock
async def test_chat_with_tools_short_circuits_on_terminal_tool_result():
    route = respx.post(CHAT_URL)
    route.mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "consult_advanced_model", "arguments": {}}}
                    ],
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )
    )

    async def executor(name, args):
        return TerminalToolResult("cloud answer, unaltered")

    result = await ollama_client.chat_with_tools(
        "qwen", [{"role": "user", "content": "hi"}], [], executor
    )

    assert result == {
        "content": "cloud answer, unaltered",
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }
    # Only the one round-trip that decided to call the tool — no second
    # call to relay the terminal result back through the local model.
    assert route.call_count == 1


@respx.mock
async def test_chat_with_tools_terminal_result_takes_priority_over_other_calls_same_turn():
    """If the model fires multiple tool calls in one message (a normal data
    tool plus consult_advanced_model), the terminal result still short-
    circuits the turn — the non-terminal tool's result was already appended
    to the message history, it just doesn't get a further round-trip."""
    route = respx.post(CHAT_URL)
    route.mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "get_daily_nutrition", "arguments": {}}},
                        {"function": {"name": "consult_advanced_model", "arguments": {}}},
                    ],
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )
    )

    async def executor(name, args):
        if name == "consult_advanced_model":
            return TerminalToolResult("cloud answer")
        return "some nutrition data"

    result = await ollama_client.chat_with_tools(
        "qwen", [{"role": "user", "content": "hi"}], [], executor
    )

    assert result["content"] == "cloud answer"
    assert route.call_count == 1
