# LifeOS — Progress Log & Next Steps

**Last updated:** 2026-07-22
**Status:** Well ahead of the roadmap's Week 1 milestone on raw capability. Finance MCP is now fully live, and a first (partial) proactive-messaging mechanism exists — see Recommended Next Steps for what's still missing.

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
- **Finance** (`app/finance_client.py`): `log_expense` (auto-creates categories), `add_expense_category` (optional budget), `get_spending_summary` (today/week/month totals, per-category breakdown, budget % when set), `list_recent_expenses` + `delete_expense`, `list_bills`/`add_bill`/`update_bill`/`delete_bill`, `log_bill_payment`, `get_fixed_monthly_overhead`. 14 categories seeded (transportation, fuel, groceries, subscriptions, bills, loans, mortgage, insurance, savings, kids, clothes, events, gadgets, other); the system prompt lists existing categories so the model reuses them instead of inventing near-duplicates.
  - **Recurring bills auto-post.** A bill is described once (name, amount, due day, category, recurrence); every time a finance tool runs, any bill whose due date has passed is logged as a real expense and rolled forward to the next cycle automatically — no manual re-entry.
  - **Variable-amount bills** (`amount_is_fixed=false`, e.g. utilities) don't auto-post a guessed number — they wait for `log_bill_payment` to confirm the actual amount, then roll forward.
  - Real data on file: Mortgage (2550 PLN/12th), YouTube Premium, iCloud+, Claude Subscription (all monthly subscriptions).

### Proactive scheduler (`app/scheduler.py`) — first step toward the spec's core differentiator
- A plain `asyncio` loop started from `main.py`'s lifespan (no new dependency — deliberately not n8n or APScheduler) sleeps until 08:00 Europe/Warsaw, runs daily finance checks, then repeats
- Sends a Telegram reminder exactly `reminder_days_before` days ahead of a bill's due date; auto-posts fixed bills same as the on-demand path; nudges (daily, until resolved) for variable bills awaiting confirmation
- Budget alerts: any category with a `monthly_budget` set gets a one-time Telegram alert per month at the 80% and 100% thresholds (deduped via `expense_category.last_budget_alert`)
- **This is not yet the spec's morning brief / evening review** — it only carries finance checks so far. Extending it to compose and send the actual 06:45 brief / 21:00 review is the next step (see Recommended Next Steps).

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
- **Ahead of the roadmap's own week boundaries.** The 6-week plan puts LLM wiring at Week 4 (Orchestrator); tool-calling, memory, and persona already exist. The formal 3-agent split (Orchestrator/Coach/Ops) does not — everything today is one undifferentiated chat path. Deliberately not building it yet: the single Qwen tool-calling path already routes and handles tone fine, and splitting into 3 model-backed agents now would be speculative architecture with no observed limitation forcing it.
- **In-process `asyncio` scheduler instead of n8n cron.** n8n is running as a service but unused; a plain daily-loop task inside the FastAPI app (`app/scheduler.py`) was simpler than configuring n8n workflows for this first proactive use case, and adds no new dependency. Revisit if scheduling needs grow complex enough to want a real workflow UI.
- **Expense categories are freeform, not a fixed enum.** Spec's §7.5 implies a closed category list; instead categories are created on demand (seeded with 14 common ones as a starting menu) and the system prompt lists existing ones so the model prefers reuse over inventing near-duplicates. This was explicit user preference over a fixed schema.

## 4. Known gaps / things observed

- **Tool-calling isn't 100% reliable.** During calendar testing, one identical request produced a real tool call in isolation but appeared to skip tool-calling entirely in one live run (see conversation history around the "family movie night" test) — a 35B local model's tool-choice decisions have real variance. No mitigation built yet beyond "the reply always states what happened, so mistakes are visible."
- **No automated tests.** Every verification so far has been manual (direct API calls, live Telegram messages). Issue #4 (pytest + CI) is still open.
- **Proactive messaging exists but is finance-only.** The spec's key differentiator (assistant messages first) is now real for bill reminders/budget alerts, but the actual morning brief (06:45) and evening review (21:00) from the spec still don't exist. See recommendation below.
- **The LLM will confabulate a fake system limitation rather than admit a missing tool.** Caught it telling the user "the system doesn't allow deleting expense history" when the real issue was simply that no delete tool existed yet. Added an explicit prompt rule ("say so plainly, never claim a fake limitation") and the missing tools, but worth watching for the same pattern elsewhere as new capability gaps get hit.

---

## 5. Recommended next steps

In rough priority order, with reasoning:

### 1. Extend `app/scheduler.py` into the real morning brief / evening review — highest leverage
The daily loop, Telegram send, and per-day trigger already exist and are proven (finance reminders/alerts use them today) — what's missing is composing the actual 06:45 brief (calendar + goals + gym day + fixed monthly overhead) and 21:00 review (5-7 questions) and sending them from the same loop instead of just finance checks. This is now mostly composition work on top of an already-working trigger, not new infrastructure.

### 2. Semantic memory / fact-saving with confirmation
Right now "remember X" tools (`update_saved_place`) write immediately with no review step — fine for places, riskier for arbitrary personal facts. The spec's `user_fact` table + confirm flow (§6.3, §8.7) would make the persona genuinely improve over time instead of only knowing what was manually seeded.

### 3. Test harness + CI (issue #4)
Not urgent functionally, but every feature so far has only ever been manually verified — a regression in `prompts.py`, `calendar_client.py`, or now `finance_client.py`'s bill-rollover math wouldn't be caught until someone notices a bad Telegram reply. Worth doing before the codebase gets much bigger.

### 4. Redaction Gateway (issue #10)
Correctly deferred — no cloud calls exist yet to redact against. Becomes urgent the moment OpenRouter/Claude gets wired in for harder reasoning (spec's Week 4-5 "coaching decisions, plan changes").

### 5. Second instance for wife
Decided approach: a fully separate deployment (own DB, own Telegram bot token, own Google Calendar OAuth refresh token), reusing the existing Ollama server and Google Maps API key as-is. Zero schema changes needed since nothing here is multi-tenant. Not started — parallel track, doesn't block anything above.

**Not recommended yet:** Gym/food/study MCPs (Week 3) — real value, but lower leverage than finishing the proactive-messaging loop, and would follow the same now-proven tool-calling pattern quickly once picked up.
