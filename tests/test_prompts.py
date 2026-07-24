"""Regression test for a real routing bug found via live usage: the system
prompt's original catch-all ("only call a tool when the question needs live
data or a change") was written before consult_advanced_model existed, and
told Qwen not to call it for meal proposals/advice — the exact opposite of
its purpose. Asked live to propose a meal from fridge contents, it answered
directly instead of routing to OpenRouter. Fixed by carving out an explicit
exception in app/prompts.py; this pins that exception down."""

from app.prompts import TOOL_GUIDANCE


def test_final_catchall_does_not_block_consult_advanced_model():
    guidance = TOOL_GUIDANCE
    assert "consult_advanced_model" in guidance

    catchall_start = guidance.index("Only call a data/action tool")
    catchall = guidance[catchall_start:]
    assert "consult_advanced_model" in catchall
    assert "always warrants calling consult_advanced_model" in catchall


def test_calendar_writes_require_an_explicit_specific_ask():
    """Regression test for a live incident: asked for general health/routine
    advice (with a vague, trailed-off mention of 'maybe a calendar'), the
    local model replied that it had added five calendar events — it hadn't
    actually called create_calendar_event at all, a pure hallucination. The
    guidance now explicitly says advice/routine requests are not scheduling
    requests, regardless of an incidental calendar mention."""
    guidance = TOOL_GUIDANCE
    assert "NOT a request to create real events" in guidance
    assert "explicit, specific scheduling ask" in guidance
