# LifeOS Web App — Plan

**Status:** Built. This doc is the original design as approved; treat it as historical context for *why* the app is shaped this way. For what's actually live today (vision, usage dashboard, the dark-only redesign, etc.), see `02-PROGRESS.md` §1.

## Why

The Telegram bot is currently the only UI. Three problems with that:

1. **One conversation thread.** [app/history.py](app/history.py) keeps a single rolling history per Telegram chat_id (last 10 exchanges, 6h TTL). Test messages and real usage share the same thread — there's no way to keep them apart.
2. **No sessions.** History isn't persisted anywhere durable, and there's no concept of multiple named/switchable conversations — only "the current 6-hour window."
3. **No DB visibility.** 30 tables in [app/models.py](app/models.py), zero admin surface. Every read or edit has to go through the LLM, which has already fabricated at least one fake write confirmation (see `02-PROGRESS.md` §4) — not something to trust for correcting your own data.

## Decisions made

| Question | Decision | Why |
|---|---|---|
| Chat frontend | Custom React + Vite SPA | Full control, matches "looks like any other chatbot," no new runtime dependency beyond a build step |
| DB admin | Adminer container, localhost-only | Full CRUD on all 30 tables for near-zero build effort; kept off the public ngrok tunnel since raw SQL access is a bigger risk than the app itself |
| Auth | Google OAuth login, **not** shared multi-tenancy | See below |
| Telegram bot | Stays, unchanged from the user's perspective | Still the proactive/push channel (morning brief, bill reminders, etc.) |

### Auth: Google Sign-In as a login screen, not shared data

This deployment stays **single-tenant** — one Postgres DB, one persona, one set of goals/expenses/health data, scoped to one person. That was already decided in `02-PROGRESS.md` §5 ("second instance for wife": a fully separate deployment, own DB/bot/OAuth token, because nothing in the schema is multi-tenant).

Google OAuth here only replaces the login *mechanism* (password → "Sign in with Google"), gated by an allow-list of Google account emails (`WEBAPP_ALLOWED_EMAILS`, same pattern as `TELEGRAM_ALLOWED_USER_ID`). It does **not** mean multiple people share this instance's data. If a family member wants their own LifeOS, they get their own deployment — own DB, own Telegram bot, own Calendar OAuth, own `WEBAPP_ALLOWED_EMAILS` — same as already planned. Making them true tenants of one instance would mean adding `user_id` to essentially every table (goals, expenses, health metrics, chat sessions), reworking the persona builder, tool executors, and scheduler to run per-user — a project on the scale of the rest of LifeOS combined, and explicitly out of scope here.

## Architecture

Everything stays inside the existing FastAPI app and single Postgres instance — no new services except Adminer. The SPA builds to static files served by FastAPI itself, riding the same ngrok domain as the Telegram webhook (different paths, no new tunnel).

```
                         ngrok (your-domain.ngrok-free.dev)
                                     |
                              FastAPI app:8000
        +---------------+-----------+-----------+------------------+
   /telegram/webhook   /api/*                  / (SPA static)   /apple-health/sync
        |                 |                       |
        |            chat_service.py (shared core) |
        |                 |                       |
        +-----------------+-----------------------+
                           |
                    Postgres (+ chat_session, chat_message tables)
                    Redis (kept for location cache only)

Adminer -- separate container, 127.0.0.1:8081 only, not on the ngrok tunnel
```

## Schema changes

New Alembic migration adding two tables:

- **`chat_session`**: `id` (uuid), `channel` (`web` | `telegram`), `title` (nullable, auto-filled from the first message), `created_at`, `updated_at`, `archived` (bool)
- **`chat_message`**: `id`, `session_id` (FK), `role`, `content`, `tool_calls` (json, nullable), `tokens` (int, nullable), `created_at`

This becomes the source of truth for conversation history, replacing Redis. The Telegram bot keeps using one persistent `channel='telegram'` session (identical behavior to today from the user's side); the web app can create unlimited disposable sessions.

## Backend changes

1. **Extract `chat_service.py`.** Pull the system-prompt-build + `ollama_client.chat_with_tools` + interaction-log logic out of `routers/telegram.py::_reply_with_ollama` into `app/chat_service.py::run_turn(session_id, text) -> str`. Both Telegram and the new web API call this — pure refactor, no behavior change, verified against live Telegram before moving on.
2. **Generalize `tools.py::make_executor`.** Currently keyed by Telegram's numeric `chat_id` (used for the cached-location lookup, etc.) — rename the key to a generic context id so web sessions can use it too.
3. **Auth.** Google OAuth2 authorization-code flow implemented directly with `httpx` (matching the existing pattern in `scripts/google_calendar_auth.py` — no new OAuth library dependency). Token verified via Google's `tokeninfo` endpoint, email checked against `WEBAPP_ALLOWED_EMAILS`, then a signed httpOnly session cookie (JWT, `WEBAPP_SECRET_KEY`) is issued. Needs a new **Web application**-type OAuth client in the same Google Cloud project as Calendar (the existing client is Desktop-app type and can't do a browser redirect flow).
4. **API surface** (`/api/*`, all behind the auth cookie except login):
   - `GET/POST /api/auth/*` — OAuth redirect + callback + logout
   - `GET/POST /api/sessions`, `PATCH/DELETE /api/sessions/{id}` — list/create/rename/archive
   - `GET /api/sessions/{id}/messages` — paginated history
   - `POST /api/sessions/{id}/messages` — send a message, get the reply (plain request/response first; SSE/WebSocket token streaming is a stretch goal once this works)
5. **Rate-limit `/api/auth/*`** — small in-memory counter is enough at this scale, but it's now a public-internet login endpoint.

## Frontend

React + Vite + Tailwind. Sidebar (session list, new-chat button, rename/delete) + main pane (message bubbles, input box) + a "Sign in with Google" landing page. `npm run build` outputs into `app/static/`; FastAPI mounts it — one deployable unit, no CORS to manage, same "one Docker service" shape as everything else in this repo.

## Rollout order

| Phase | Work | Est. |
|---|---|---|
| 0 | Extract `chat_service.py`, verify Telegram unchanged | 0.5–1 day |
| 1 | `chat_session`/`chat_message` migration | 0.5 day |
| 2 | Point Telegram at the new tables instead of Redis history | 0.5–1 day |
| 3 | Google OAuth login + session cookie + rate limiting | 1–1.5 days |
| 4 | `/api/sessions*` endpoints, curl-tested | 1–2 days |
| 5 | React/Vite SPA: login, session sidebar, chat thread | 4–6 days |
| 6 | Adminer container + compose wiring + README update | <0.5 day |
| Stretch | ~~SSE streaming~~ (done), auto-generated session titles (done), ~~surfacing scheduler proactive-sends in the web feed~~ (done) | — |

Roughly 1.5–2 weeks part-time.

## Risks / things to watch

- **Bigger attack surface.** This is the first genuinely internet-facing, stateful, authenticated surface in the app (health-sync is token-gated but stateless). Worth API-level tests here even before tackling the broader "no automated tests" gap (issue #4).
- **Redis's role shrinks** to just the location cache once chat history moves to Postgres — fine, not worth removing Redis entirely.
- **Don't let this creep into multi-tenancy.** If a second real user is ever wanted on *this* instance rather than a separate deployment, that's a scope decision to make explicitly, not something to back into by reusing the OAuth allow-list for more than one email.
