# LifeOS — Progress Log & Next Steps

**Last updated:** 2026-07-22
**Status:** Well ahead of the roadmap's Week 1 milestone on raw capability. Finance MCP and Apple Health sync are both fully live, and the proactive scheduler's morning/evening messages now genuinely fold together health, calendar (primary + family), goal progress, weight, and a real computed train commute — not just a health-only ping. A second UI (web app, multi-session, Google-authenticated, mobile-responsive with dark mode) now sits alongside the Telegram bot — see §1 "Web app" below and `03-WEBAPP-PLAN.md`. See Recommended Next Steps for what's still missing.

This document is a running record of what's actually been built, as a supplement to `00-MASTER_SPEC.md` (the locked design) and `01-HANDOFF.md` (quick context). Update it as work lands — it's meant to answer "what's real right now" without having to read every commit.

---

## 1. What's live right now

### Web app (new — see 03-WEBAPP-PLAN.md for design)
- Second UI alongside Telegram: a React/Vite SPA served by FastAPI itself (`webapp/` → built into `app/static/`, mounted at `/`), same persona/tools/data, single-tenant. Live-verified end-to-end via a real browser session: login gate, session create/rename/delete, Markdown-rendered replies, sidebar sorted by recency.
- `app/chat_service.py` — the system-prompt + tool-calling + logging core extracted out of the Telegram router, now shared by both surfaces so they can't drift apart. `app/prompts.py::system_prompt` is channel-aware: Telegram still gets the "no Markdown" instruction, the web app gets a Markdown-friendly one.
- `chat_session`/`chat_message` tables (Postgres) replace Redis as the durable history store; `app/history.py` (Redis-based) is retired. Telegram keeps exactly one persistent `channel='telegram'` session (matches its old single-thread behavior exactly — verified via live smoke test, including `/reset`); the web app can create unlimited sessions via `/api/sessions`.
- Auth is Google OAuth (`app/auth.py`, `app/routers/auth.py`), gated by a `WEBAPP_ALLOWED_EMAILS` allow-list, signed session cookie (`itsdangerous`). This is a login-mechanism swap only, **not** multi-tenancy — every allowed email sees the same single-tenant data. A second real person still means a second full deployment, per §5 below.
- `/api/sessions*` (`app/routers/sessions.py`, `app/chat_store.py`) — full CRUD + messaging, channel-scoped so the web API can't touch Telegram's session. Auto-titles a session from its first message.
- Adminer added to `docker-compose.yml`, bound to `127.0.0.1:8081` only — deliberately never routed through the ngrok tunnel (raw SQL edit access is a bigger risk than the app itself). Solves "no way to see/edit the DB without asking the AI" directly.
- **Google OAuth is fully live** — the Web application client is created, `.env` is filled in, and login has been verified end-to-end with the real account (not just a manually-minted test cookie).
- **Mobile-responsive** — the sidebar is a slide-in drawer with a hamburger + backdrop below the `md` breakpoint (confirmed broken before this on a real 375×812 viewport — the fixed sidebar ate most of the screen). Rename/archive icons, which were hover-only (unreachable on any touch device), are now always visible on mobile and hover-reveal only on desktop.
- **Dark mode** — toggle in the sidebar footer, defaults to OS preference, persisted in `localStorage`. Covers login screen, sidebar, bubbles, markdown, and the archived-sessions panel.
- **Soft-delete safety net** — the sidebar ✕ now archives (`chat_session.archived`) instead of hard-deleting, with an "Archived" panel to restore or permanently purge. Added after a real incident: an instruction to "test the delete button on a test session" led to a user's actual conversation being hard-deleted, unrecoverable, because by that point no test sessions were left. Worth remembering as a reason for the safety net existing at all.
- **iOS Safari auto-zoom fixed** — the chat input and sidebar rename input were `text-sm` (14px), under iOS's 16px auto-zoom-on-focus threshold; bumped to 16px below the `sm` breakpoint (unchanged 14px on desktop). Found via real iPhone 13 Pro Max testing.
- **Dev workflow quirk worth remembering:** `docker-compose.yml` bind-mounts `./app` over the container's app directory (for live Python editing), which also shadows whatever the Docker image's multi-stage build baked into `app/static/`. So a frontend change needs `npm run build` run directly (from `webapp/`) to land in the bind-mounted `app/static/` — rebuilding the image alone won't update what the running dev container serves.

### Test harness + CI (new — closes issue #4)
- `tests/` (pytest, 87 tests) against a dedicated `lifeos_test` Postgres database — created automatically, table-truncated between tests, never touches the real dev DB. Covers `chat_service` (mocked Ollama), `finance_client`'s bill-rollover/budget-alert math, `tools.py`'s tool-dispatch table, the full `/api/sessions` CRUD+messaging API, that `alembic upgrade head` applies cleanly against a brand-new database, and now `calendar_client`/`maps_client`/`health_client` too (see below).
- `.github/workflows/tests.yml` runs the suite on every push/PR against real Postgres (pgvector image) + Redis service containers.
- Run locally: `docker compose run --rm app sh -c "pip install -r requirements-dev.txt && pytest -v"`. `requirements-dev.txt`, `pytest.ini`, and `tests/` are bind-mounted into the app container (same pattern as `alembic/`) so edits don't need an image rebuild.
- **The three external-API modules now have coverage too.** `health_client` needed no mocking (it only parses already-delivered Apple Health JSON into the DB) — tests directly regress the two real bugs from §4 (kJ-vs-kcal, sleep hours-vs-minutes). `calendar_client`/`maps_client` hit Google's APIs live, so `respx` (new dev-only dependency) mocks the HTTP layer — including a direct regression test for the arrival-time sorting bug (§ Maps: arrival-time queries) that used to return the earliest departures instead of the latest ones that still make the deadline, and a check that `list_today_events`'s past/upcoming labeling (the thing the model couldn't reliably work out itself) is correct.
- **A real async-testing gotcha, worth remembering:** `redis_client` caches its client at module level, bound to whichever event loop was active when first created. Since each pytest-asyncio test function gets its own event loop by default, reusing that cached client in a later test throws "attached to a different loop." Fixed by resetting `redis_client._client = None` in an autouse fixture so every test gets a client bound to its own loop — same class of bug as any other module-level singleton tied to async infrastructure.

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
- **Apple Health** (`app/health_client.py`, `app/routers/health_sync.py`): `POST /apple-health/sync` receives Health Auto Export's REST API JSON export (bearer-token gated — the endpoint is otherwise public through the ngrok tunnel like everything else), parses it into `metric_daily` (steps, active/resting kcal, sleep hours, resting HR, avg HR, HRV, weight) and `apple_workout` (type, duration, kcal, distance, avg/max HR, deduped by Apple's workout id). `get_health_summary(period)` tool mirrors `get_spending_summary` for on-demand "how was my week" questions.
  - Live-verified against a real payload from the phone, including two real parser bugs found and fixed: `active_energy`/`basal_energy_burned` arrive in **kJ** (converted to kcal, respecting each metric's own declared `units` field — same conversion needed on the `activeEnergyBurned` workout field, initially missed there too), and `sleep_analysis`'s `totalSleep` arrives in **hours** already, not minutes.
  - The app's REST API automation needs `step_count`, `resting_heart_rate`, `basal_energy_burned` explicitly added to its selected metrics, and a **separate** automation (different "Typ danych") for workouts — one automation only covers one data-type category.
  - Also tested the app's alternate MCP server mode (`Server` tab, live pull instead of scheduled push) — works, but the server stops the instant the app is backgrounded, so it's only viable for on-demand foreground queries, not anything scheduled. Kept the webhook as the reliable always-on path; the MCP route is a possible future supplementary source, not wired in yet.

### Proactive scheduler (`app/scheduler.py`) — now sends real morning/evening messages
- Three independent daily `asyncio` loops (no new dependency — deliberately not n8n or APScheduler), each sleeping until its own next occurrence in Europe/Warsaw: **07:00 morning motivation**, **08:00 finance checks** (unchanged from before), **21:00 evening feedback**
- Morning/evening are both Qwen-composed and now fold together: health snapshot (yesterday for morning, today for evening), today's/tomorrow's calendar across **both primary and family calendars**, this week's gym/squash goal progress vs. actual synced workouts (`health_client.get_workout_goal_progress`), latest synced weight vs. the weight goal, and — when an "Office"-titled calendar event exists — a real computed train commute (see below)
- **Calendar events are labeled past/upcoming in code, not left for the model to work out.** `calendar_client.list_today_events` compares each event's start time against "now" and explicitly tags it `(already started/passed)` or `(upcoming)` — the model was not reliably cross-referencing a bare event timestamp against the separate "current time" line elsewhere in the prompt on its own, so it's computed deterministically instead (same philosophy as the Markdown fix).
- **Auto-computed office commute** (`scheduler._office_commute_note`): detects an "office" event on the relevant day and calls `get_train_departures` with the new `arrival_time_iso` option (below) to find real trains that arrive on time, lists all of them (not just one) so the choice stays with the user.
- Finance checks: Telegram reminder exactly `reminder_days_before` days ahead of a bill's due date; auto-posts fixed bills same as the on-demand path; nudges (daily, until resolved) for variable bills awaiting confirmation; budget alerts at 80%/100% thresholds (deduped via `expense_category.last_budget_alert`); also now checks `health_client.check_sync_health()` and warns if Apple Health hasn't synced in 2+ days.
- **Telegram output is sanitized, not just prompted.** The model repeatedly ignored a "no Markdown" system-prompt instruction (kept generating `**bold**`/`#` headers, which Telegram displays as literal asterisks/hashes with no `parse_mode` set) — fixed by stripping Markdown syntax deterministically in `telegram_client.send_message` itself, the actual send boundary, rather than continuing to rely on prompt compliance.
- **Still not the full spec evening review** — it's a one-way wrap-up, not the spec's interactive 5-7 question flow. See Recommended Next Steps.

### Maps: arrival-time queries (`app/maps_client.py`)
- `get_train_departures` now accepts `arrival_time_iso` (in addition to the existing `departure_time_iso`) — answers "what time do I need to leave to be there by X" using Google Directions API's `arrival_time` parameter, correctly returning the **latest** valid departures (sorted descending, then re-sorted for display), not the earliest ones hours before the deadline, which was the actual bug caught during testing.

### GitHub
- Issues #17 (retroactive Week 1 tracking), #5 (secrets policy), #16 (Finance MCP), #7 (bill reminders) closed
- Issues #14 (morning brief composer) and #15 (evening review flow) commented with partial-progress status — real brief/wrap-up now exists, but not the full Orchestrator-agent/interactive-review scope, left open
- PR #18 (Maps tool-calling), #19 (Finance MCP), #20 (Apple Health sync) merged
- Commits pushed to `master`, full history below

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
- **Automated tests now exist** (issue #4, closed) — `tests/` + GitHub Actions, see "What's live" below, now including `calendar_client`/`maps_client`/`health_client`. Still true that most of this codebase's history was built on manual verification alone; scheduler.py and the routers themselves still have no direct test coverage.
- **Proactive messaging exists but is finance-only.** The spec's key differentiator (assistant messages first) is now real for bill reminders/budget alerts, but the actual morning brief (06:45) and evening review (21:00) from the spec still don't exist. See recommendation below.
- **The LLM will confabulate a fake system limitation rather than admit a missing tool.** Caught it telling the user "the system doesn't allow deleting expense history" when the real issue was simply that no delete tool existed yet. Added an explicit prompt rule ("say so plainly, never claim a fake limitation") and the missing tools, but worth watching for the same pattern elsewhere as new capability gaps get hit.
- **Third-party data export formats need real-payload verification, not just docs.** The Health Auto Export JSON schema docs showed generic examples that didn't match this account's actual units (kJ vs kcal, hours vs minutes for sleep) — both silently produced wildly wrong numbers (7164 kcal for one day) until checked against a real captured payload. Worth remembering for any future third-party integration: verify against a live sample, don't trust the reference docs' example values.
- **Prompt-only instructions to the local model are not reliable enough for hard constraints.** Told it not to use Markdown (Telegram doesn't render it) directly in the system prompt — it ignored this twice in a row. Fixed by enforcing it in code instead (strip Markdown at the `send_message` boundary). General lesson: anything that must always hold should be enforced deterministically in code, not left to model compliance, even with explicit instructions.
- **The model will hallucinate a full, convincing action confirmation without ever calling the tool.** Asked it to create a calendar event; it replied "Done — added Work@Backbase Office 09:00-17:00 and Gym 17:00-18:00" with specific plausible times, using facts already in its persona context (the real Backbase office). Checked Redis chat history + Ollama call count: only one round-trip happened, meaning zero tool calls — the whole confirmation was invented. The actual calendar was empty. This is worse than the earlier "fake system limitation" confabulation because it fabricates a *successful outcome* with specific details, not just a refusal. Added explicit prompt language ("never reply as if you created/updated/deleted something unless you actually called the tool this turn"), but per the lesson above, prompting alone is not a complete fix — always verify a claimed write against the actual data source when in doubt, don't trust the chat reply.
- **An empty model reply crashes the Telegram send with zero visible feedback.** Same incident: the follow-up message's reply came back as `""`, which Telegram's `sendMessage` rejects with 400 — and since nothing caught that exception, the user's message was silently dropped with literally no reply, visible only in server logs. Fixed with a guard in `routers/telegram.py` that substitutes a fallback message when the reply is empty, and wrapped the final `send_message` call in try/except so a Telegram-side failure can't crash the background task silently again.

---

## 5. Recommended next steps

In rough priority order, with reasoning:

### 1. The spec's actual interactive 5-7 question evening review — highest leverage remaining
Morning/evening messages are now genuinely rich (health + calendar + goals + weight + commute), but the evening one is still a one-way wrap-up, not the spec's interactive review that captures the day's answers back into the DB (mood, family time, reflections). Everything needed (trigger, Telegram send, persona composition) is proven; this is a conversational-flow design problem, not new infrastructure.

### 2. Semantic memory / fact-saving with confirmation
Right now "remember X" tools (`update_saved_place`) write immediately with no review step — fine for places, riskier for arbitrary personal facts. The spec's `user_fact` table + confirm flow (§6.3, §8.7) would make the persona genuinely improve over time instead of only knowing what was manually seeded.

### 3. ~~Test harness + CI~~ — done (issue #4, closed)
`tests/` (pytest, 87 tests) + `.github/workflows/tests.yml` now cover `chat_service`, the `/api/sessions` API, `finance_client`'s bill-rollover/budget logic, `tools.py`'s dispatch table, `alembic upgrade head`, and — via `respx`-mocked HTTP — `calendar_client`, `maps_client`, and `health_client` too, including direct regressions for the arrival-time sorting bug and the kJ/sleep-units bugs from §4. Runs against a dedicated `lifeos_test` database, never the real one. Not exhaustive — `scheduler.py` and the routers themselves still have no direct coverage.

### 4. Redaction Gateway (issue #10)
Correctly deferred — no cloud calls exist yet to redact against. Becomes urgent the moment OpenRouter/Claude gets wired in for harder reasoning (spec's Week 4-5 "coaching decisions, plan changes").

### 5. Second instance for wife
Decided approach: a fully separate deployment (own DB, own Telegram bot token, own Google Calendar OAuth refresh token), reusing the existing Ollama server and Google Maps API key as-is. Zero schema changes needed since nothing here is multi-tenant. Not started — parallel track, doesn't block anything above.

**Not recommended yet:** Gym/food/study MCPs (Week 3) — real value, but lower leverage than finishing the proactive-messaging loop, and would follow the same now-proven tool-calling pattern quickly once picked up.
