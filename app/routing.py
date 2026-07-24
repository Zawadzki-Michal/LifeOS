"""Deterministic local-vs-cloud routing for one chat turn.

Qwen's own tool-choice judgment has documented variance (02-PROGRESS.md
§4 — it has both skipped obvious tool calls and hallucinated ones that
never happened). Rather than trying to make that detection smarter, the
user marks which messages need the local tool-calling model themselves:
a "Local:" prefix forces the local path (calendar, expenses, health,
nutrition — anything that reads/writes real data via a tool); anything
else skips the local model entirely and goes straight to the cloud model,
since only the local path has tool access today. This also fixes the
"why did a simple question take over a minute" complaint for the common
case of a question that never needed a tool in the first place.
"""

import re

_LOCAL_PREFIX_RE = re.compile(r"^\s*local\s*:\s*", re.IGNORECASE)


def strip_local_prefix(text: str) -> tuple[bool, str]:
    """Returns (is_local, text_with_prefix_removed)."""
    match = _LOCAL_PREFIX_RE.match(text)
    if match:
        return True, text[match.end():].lstrip()
    return False, text
