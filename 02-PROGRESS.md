# LifeOS — Progress Log & Next Steps

**Last updated:** 2026-07-21
**Status:** Well ahead of the roadmap's Week 1 milestone on raw capability, behind on the "proactive" core differentiator (see Recommended Next Steps).

This document is a running record of what's actually been built, as a supplement to `00-MASTER_SPEC.md` (the locked design) and `01-HANDOFF.md` (quick context). Update it as work lands — it's meant to answer "what's real right now" without having to read every commit.

---

## 1. What's live right now

### Infrastructure
- Docker Compose stack: Postgres 16 + pgvector, Redis, n8n, FastAPI app — all running (`docker-compose.yml`)
- Full V1 DB schema (27 tables from MASTER_SPEC §7) via SQLAlchemy models + Alembic migrations (`app/models.py`, `alembic/versions/`)
- Public ingress via an ngrok tunnel on a free reserved static domain (stable across restarts) — not Cloudflare as originally speced, since it needed no domain purchase or account setup (see §3, Deviations)
- Google Calendar OAuth (Desktop app client, refresh token) — verified working
- Google Maps API (Directions) — verified working

### Telegram bot (`@LifeOS88_bot`)
- Webhook-based, locked to a single allowed Telegram user ID
- Every message round-trips to local Qwen (`qwen3.6:35b-a3b` via Ollama) with:
  - **Multi-turn memory** — Redis-backed, last 10 exchanges, 6h TTL, `/reset` command to clear
  - **DB-driven persona** — system prompt built fresh each message from `user`, `goal`, `household_member`, `user_fact` tables (not hardcoded), plus current date/time so the model can resolve "Wednesday"/"tomorrow" itself
  - **`interaction_log` writes** — every exchange logged with real token counts from Ollama's response
- Seeded profile data: user (Michał), 8 goals from MASTER_SPEC §2, household (wife Ania, kids Martina/Jakub), a starting weight anchor, occupation/squash-partner facts, saved places (home, mom, work)

### Tool-calling (Qwen calls real tools via Ollama's `/api/chat` tools API)
- **Maps**: driving directions (resolves saved place names like "mom"/"work"), multi-departure Polish train lookups, a combined `plan_train_commute` for "heading to work by train soon", and `update_saved_place` so the model can save new places from plain conversation
- **Calendar**: full CRUD — `list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`. Defaults to the primary calendar; "family" resolves to the shared Family calendar by name. Editing works by natural description (model lists events first to find the id). Verified against the real API including a real timezone-display bug fix (Google's create/update responses echo the *calendar's* default timezone, not the event's — confirmations now use the values we sent, not Google's echoed response)
- Location sharing (Telegram's native location message) is captured and used as the origin for driving directions

### GitHub
- Issue #17 (retroactive Week 1 tracking) and #5 (secrets policy) closed
- PR #18 (Maps tool-calling, opened by a separate session) merged
- 9 commits pushed to `master`, full history below

---

## 2. Commit history (this build)

| Commit | What |
|---|---|
| `a704223` | Docker stack, full DB schema + migration, live Telegram echo bot |
| `8445619` | Swapped Cloudflare Quick Tunnel → ngrok static domain; wired Telegram → Qwen via Ollama |
| `e02145a` | (PR #18, merged) Maps tool-calling: driving directions, train departures |
| `27a50fb` | Chat memory, DB-driven persona, `interaction_log` |
| `a6cde17` | Merged PR #18 — hand-resolved conflicts against the memory/persona work |
| `5ec94fe` | Saved places, home address, combined train-commute tool |
| `caa1d1f` | Train departures: return next 3-5, not just 1 |
| `c4228ed` | Google Calendar OAuth credentials + one-time auth script |
| `9ce2392` | Full Calendar CRUD via tool-calling + timezone-display bug fix |

---

## 3. Deliberate deviations from MASTER_SPEC

Worth knowing about so nobody "fixes" these back by accident:

- **ngrok instead of Cloudflare Tunnel** for ingress. Spec named Cloudflare; ngrok's free static domain needed no domain purchase and is stable across restarts (Cloudflare's free tier is a random URL that changes every restart). Functionally equivalent; can revisit if a domain gets added to Cloudflare later.
- **Live API calls, not synced local tables**, for Maps and Calendar. Spec's §7.3 defines `calendar_source`/`calendar_event` for a synced cache; we call Google live instead — simpler, always current, no staleness/sync-job complexity for a single-user chat interface. Revisit only if a future feature (e.g. weekly reports) needs to query calendar data without hitting the API each time.
- **No propose-then-confirm step for calendar/place writes.** Spec's `propose_event` implies a draft-then-confirm flow. Current tools act immediately and always state the exact result in the reply, so mistakes are visible and easy to correct with a follow-up message — this was an explicit user choice (simpler, no multi-turn "pending action" state to build), not an oversight.
- **No Redaction Gateway yet.** Everything today is 100% local (Ollama only) — no OpenRouter/cloud calls exist yet, so there's nothing to redact against. This becomes a real requirement the moment any cloud model call is added (household PII — wife's name, kids' names/ages — must never leave the box per §5.4).
- **Ahead of the roadmap's own week boundaries.** The 6-week plan puts LLM wiring at Week 4 (Orchestrator); tool-calling, memory, and persona already exist. The formal 3-agent split (Orchestrator/Coach/Ops) does not — everything today is one undifferentiated chat path.

## 4. Known gaps / things observed

- **Tool-calling isn't 100% reliable.** During calendar testing, one identical request produced a real tool call in isolation but appeared to skip tool-calling entirely in one live run (see conversation history around the "family movie night" test) — a 35B local model's tool-choice decisions have real variance. No mitigation built yet beyond "the reply always states what happened, so mistakes are visible."
- **No automated tests.** Every verification so far has been manual (direct API calls, live Telegram messages). Issue #4 (pytest + CI) is still open.
- **No proactive messaging at all.** Despite being the spec's stated key differentiator ("the assistant messages first"), the system today is 100% reactive — nothing fires without an inbound Telegram message. See recommendation below.

---

## 5. Recommended next steps

In rough priority order, with reasoning:

### 1. Proactive messaging (morning brief / evening check-in) — highest leverage
This is the spec's *entire stated differentiator* ("messages you first, on schedule") and currently doesn't exist at all — everything built so far is reactive. The pieces to build it are already sitting there: Telegram send (`app/telegram_client.py`), Qwen + persona (`app/prompts.py`), Calendar data (`app/calendar_client.py`), goals (`goal`/`goal_progress` tables). What's missing is purely a trigger: an n8n cron job (already running as a service, unused) or a simple scheduled task hitting a new `/internal/morning-brief` endpoint that composes a brief from calendar + goals and sends it via Telegram. This is mostly integration of things that already work, not new capability — good ratio of effort to payoff.

### 2. Finance MCP (expense logging) — issue #16
Directly matches the Maps/Calendar tool-calling pattern already proven twice now (fast to build a third time: a `finance_client.py` + a couple of tools for `log_expense`/`month_summary` against the `expense`/`expense_category` tables, which already exist and are unused). Immediate daily-use value, explicitly called out in the spec's success metrics ("expenses logged same evening").

### 3. Semantic memory / fact-saving with confirmation
Right now "remember X" tools (`update_saved_place`) write immediately with no review step — fine for places, riskier for arbitrary personal facts. The spec's `user_fact` table + confirm flow (§6.3, §8.7) would make the persona genuinely improve over time instead of only knowing what was manually seeded.

### 4. Test harness + CI (issue #4)
Not urgent functionally, but every feature so far has only ever been manually verified — a regression in `prompts.py` or `calendar_client.py` wouldn't be caught until someone notices a bad Telegram reply. Worth doing before the codebase gets much bigger.

### 5. Redaction Gateway (issue #10)
Correctly deferred — no cloud calls exist yet to redact against. Becomes urgent the moment OpenRouter/Claude gets wired in for harder reasoning (spec's Week 4-5 "coaching decisions, plan changes").

**Not recommended yet:** Gym/food/study MCPs (Week 3) — real value, but lower leverage than closing the proactive-messaging gap, and would follow the same now-proven tool-calling pattern quickly once picked up.
