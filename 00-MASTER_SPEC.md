# Personal Life OS — Master Specification v1.0

**Status:** Locked for V1 implementation  
**Owner:** Michał Zawadzki  
**Created:** 2026-01-19  
**Last updated:** 2026-01-19  

---

## 0. Executive Summary

Personal Life OS is a proactive AI accountability system designed for a single user (Michał, 38, engineer, Kraków, wife + 2 kids). The system reduces planning friction, tracks compound progress across gym/nutrition/finance/study/family, and pushes the user proactively rather than waiting to be pulled.

**Key differentiator:** The assistant messages first, on schedule, with opinionated coaching and structured accountability.

**V1 delivery:** 6 weeks, ~50 hours, Telegram-only interface, privacy-first hybrid local/cloud architecture.

**V1 success metric:** User self-reports "I would be worse off without this" at week 8. Binary pass/fail.

---

## 1. User & Household

### 1.1 Primary user
- **Name:** Michał Zawadzki
- **Age:** 38 (40th birthday target = Harley purchase)
- **Location:** Kraków, Poland (timezone: Europe/Warsaw)
- **Work:** Full-time engineer, 9–5, 3 days WFH, 2 days Kraków office (Mon + Tue/Thu)
- **Tech setup:** Windows PC (Ryzen 9, RTX 3090 24GB, 32GB RAM), MacBook M1 Pro (personal + work), Ollama installed
- **Language:** Polish/English mixed; assistant writes English by default, accepts Polish input and translates
- **Communication:** Telegram bot (sole interface V1)

### 1.2 Household (contextual entities, not users)
- **Wife:** Name stored in DB (PII, never leaves box), has Google Calendar (shared), Samsung/Google Calendar user
- **Martina:** 7 years old (PII, never leaves box)
- **Jacob:** 5 years old (PII, never leaves box)
- **Kids schedule:** Nursery 08:00–15:00 weekdays (hardcoded V1)

### 1.3 Privacy threat model
- **Principle-based:** No specific adversary; keep personal data local by default
- **Kids' data:** Names, ages, DOB = PII of minors, never sent to cloud models, ever
- **Wife data:** Name, calendar events = never sent to cloud, summarized as "SPOUSE" if needed
- **Finance:** Raw transactions OK to cloud (user explicitly confirmed)
- **Health:** Non-anonymized metrics OK to cloud (user confirmed)
- **Journal:** Local storage only, local analysis only
- **Disk encryption:** User to confirm BitLocker enablement (flagged, not mandatory V1)

---

## 2. Goals (First-Class Entities)

Goals drive proactive behavior. Each goal has a target, cadence, check-in rule, and progress tracking.

| Goal ID | Type | Description | Target | Cadence | Check-in Rule |
|---------|------|-------------|--------|---------|---------------|
| CKA-2026 | deadline | Pass CKA exam | By Nov 30, 2026 | Daily study hrs, 3–5 hr/week target | 3-day gap → confront in evening |
| CKAD-2026 | deadline | Pass CKAD exam (after CKA) | By Nov 30, 2026 | Daily study hrs, 3–5 hr/week target | Same |
| Weight-90 | trajectory | Lose weight 105→90 kg | 90 kg @ 0.4 kg/week (~9 months) | Weekly weigh-in | Trend divergence → nutrition review |
| Harley-40 | trajectory | Save for Harley by 40th birthday | 5–10k PLN own savings, rest loan (total ~40k PLN) | Monthly deposit tracking | Missed month → flag in weekly report |
| Gym-freq | frequency | Gym sessions | 2–3 sessions/week | Weekly | <2/week → confront |
| Squash-freq | frequency | Squash sessions | 2–3 sessions/week | Weekly | Informational only |
| Wife-time | frequency | Dedicated wife evening | 1/week | Weekly | 0 last week → nudge in Sunday report |
| Kids-activity | frequency | Weekend kids fun activity | 1/week | Weekly | 0 last week → nudge in Sunday report |

**Open items:**
- Current exact weight (to anchor trajectory) — user to provide
- CKA exam date vs. CKAD exam date (CKA first, both by Nov 30)

---

## 3. Daily Routine (Drives Scheduling)

### 3.1 Weekday (WFH: Wed, Thu, Fri)
- **06:30** Wake
- **06:45** **[ASSISTANT: Morning brief]**
- **07:00–08:00** Help kids ready, drop at nursery
- **08:00–09:00** (Option: Squash if scheduled, or gym)
- **09:00–17:00** Work from home
- **12:30** **[ASSISTANT: Kcal check-in if under-logged]**
- **15:00** Pick up kids from nursery
- **15:00–18:00** Kids time
- **17:30** **[ASSISTANT: Gym prescription if today = gym day]**
- **18:00** (Option: Gym or squash if not morning)
- **21:00** **[ASSISTANT: Evening review, 2 min, 5–7 questions]**
- **22:30–23:00** Sleep

### 3.2 Weekday (Office: Mon, Tue or Thu)
- **06:30** Wake
- **06:45** **[ASSISTANT: Morning brief with travel reminder]**
- **07:40** Leave for train to Kraków
- **09:00–17:00** Office (lunch provided)
- **15:00** (If Thu + squash: leave early, pick kids)
- **18:00** (Option: Gym or squash)
- **21:00** **[ASSISTANT: Evening review]**
- **22:30–23:00** Sleep

### 3.3 Weekend
- **Similar wake/sleep**
- **Family activity** (kids or wife focus)
- **Study time** (CKA/CKAD prep)
- **Gym/squash** flexible
- **Sunday 20:00** **[ASSISTANT: Weekly report]**

### 3.4 Quiet mode
- **Trigger phrases:** "shut up", "cisza", "not now", "quiet"
- **Suppression:** All non-emergency pushes until 21:00 evening review
- **Emergency exception:** Calendar event starting in <30 min that user would miss

---

## 4. Non-Goals (V1 Explicit Exclusions)

Confirmed by user. These are **not negotiable for V1**. Any feature request overlapping these gets deferred to V2 backlog.

- ❌ Bank / PSD2 / Open Banking integration (manual entry only)
- ❌ Work task management (Jira, Zendesk, Confluence out of scope)
- ❌ Work Google calendar integration (deferred to V1.5)
- ❌ Multi-user (wife, kids = context only)
- ❌ Native iOS app (PWA is V2, native V3+)
- ❌ Home automation, Siri/Alexa integration
- ❌ Photo food recognition, micronutrients tracking
- ❌ Bespoke workout program generation (template PPL only, progressed by rules)
- ❌ Automated backups (schema is backup-ready, automation deferred)
- ❌ Voice input/output (V2)
- ❌ Meal planning generation engine (only easy-meal suggestions on request)

**V2/V3 Backlog:** Voice in/out, PWA, bank integration, work calendar, wife as user, K8s migration, Home Assistant, Apple Health sync, Whisper local, Siri shortcuts, Temporal workflows, Harley purchase decision assistant.

---

## 5. System Architecture

### 5.1 Topology

```
┌────────────────────────────┐
│   Telegram (Michał only)   │
└────────────┬───────────────┘
             │ HTTPS webhook
  ┌──────────▼──────────┐
  │ Cloudflare Tunnel   │ (no port forwarding, free, safe)
  └──────────┬──────────┘
             │
┌─────────── Windows PC (RTX 3090, Docker Desktop) ───────────┐
│                                                              │
│  ┌────────┐  ┌────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │  n8n   │◄►│  FastAPI   │◄►│  LangGraph   │◄►│ Ollama  │ │
│  │ (glue, │  │  (Telegram │  │ (Orchestrator│  │ (Qwen   │ │
│  │  cron, │  │   adapter, │  │  Coach, Ops) │  │ 2.5 7B/ │ │
│  │  hooks)│  │   API)     │  └──────┬───────┘  │ 14B/32B)│ │
│  └───┬────┘  └──────┬─────┘         │          └─────────┘ │
│      │             │                │                       │
│      │             │          ┌─────▼──────┐  ┌──────────┐ │
│      │             │          │ OpenRouter │  │  Redis   │ │
│      │             │          │ (Claude,   │  │ (cache,  │ │
│      │             │          │  GPT)      │  │  queues) │ │
│      │             │          └────────────┘  └─────┬────┘ │
│      │             │                                │      │
│      │             └──► MCP servers ◄───────────────┘      │
│      │                 (calendar, finance, gym,            │
│      │                  food, study, goals, memory)        │
│      │                                                     │
│      └──► Google Calendar API                             │
│           Telegram Bot API                                │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  PostgreSQL 16 + pgvector                            │ │
│  │  (source of truth, all structured + episodic memory) │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### 5.2 Component Responsibilities

| Component | Role | Rationale |
|-----------|------|-----------|
| **Cloudflare Tunnel** | Ingress without port forwarding | Free, safer than DDNS, works behind NAT |
| **n8n** | Cron jobs, webhook receiver, retries, deterministic flows | Keeps non-LLM logic out of agents; user familiar |
| **FastAPI** | HTTP API, Telegram adapter, auth, structured I/O | Standard, testable, async |
| **LangGraph** | Agent state machine (Orchestrator, Coach, Ops) | Explicit graphs > implicit chains; debuggable |
| **Ollama** | Local model server (Qwen 2.5 7B/14B/32B) | Already installed, low friction |
| **OpenRouter** | Cloud escalation (Claude Sonnet for hard reasoning) | Single billing, model-agnostic |
| **PostgreSQL + pgvector** | Source of truth + vector memory | One DB > multi-store; pgvector sufficient at scale |
| **Redis** | Cache (calendar snapshots), session state, quiet-mode flag | Standard fast store |
| **MCP servers** | Tool exposure to agents (calendar, finance, gym, etc.) | Clean separation; swap agent framework later without rewriting tools |

### 5.3 Model Allocation

| Task | Model | Where | Cost |
|------|-------|-------|------|
| Intent classification, routing | Qwen 2.5 7B | Local | $0 |
| Structured extraction ("47 pln biedronka" → JSON) | Qwen 2.5 7B or 14B | Local | $0 |
| Daily brief generation | Qwen 2.5 32B | Local | $0 |
| Weekly/monthly analysis, coaching decisions, plan changes | Claude Sonnet 3.5 | Cloud (OpenRouter) | ~$5–15/mo |
| Voice transcription (V2) | Whisper large-v3 | Local | $0 |

### 5.4 Trust Zones & Redaction Policy

| Data Type | Local Model | Cloud Model | Notes |
|-----------|-------------|-------------|-------|
| Kids names/ages/DOB | ✅ | ❌ NEVER | Replace with `CHILD1`, `CHILD2` if referenced |
| Wife name | ✅ | ❌ NEVER | Replace with `SPOUSE` |
| Wife calendar events | ✅ | ❌ NEVER | Summarize to "spouse busy 18–20" |
| Michał name | ✅ | ✅ | User confirmed principle-only |
| Journal / evening reflections | ✅ | ❌ | Local storage + local analysis only |
| Finance transactions | ✅ | ✅ | User explicitly confirmed raw OK to cloud |
| Health metrics (weight, HR, sleep) | ✅ | ✅ | User confirmed non-anonymized OK |
| Study progress | ✅ | ✅ | No sensitivity |
| Gym/food logs | ✅ | ✅ | No sensitivity |

**Redaction Gateway:** Middleware between LangGraph and OpenRouter. Every outbound cloud call passes through. Policy is per-domain, code-enforced, unit-tested. All cloud interactions logged in `interaction_log` with `redaction_applied` fingerprint for audit.

### 5.5 Availability & Failure Modes

- **Uptime:** PC uptime = system uptime (V1 PoC acceptable)
- **Failure mode:** If morning brief cron fails (PC off), n8n retries when PC returns and sends "Late brief" tagged. No silent drops.
- **Migration path:** Move n8n + FastAPI + Postgres to $5 Hetzner VPS; keep Ollama on PC exposed via Cloudflare Tunnel for on-demand inference. Cutover is one config change.
- **Cloud budget:** ~$5–20/month (OpenRouter + optional VPS)

---

## 6. Agent Architecture

### 6.1 Three Agents (Honest Boundaries)

#### Orchestrator
- **Model:** Qwen 2.5 14B (local, routing); Claude Sonnet (cloud, hard planning)
- **Job:** Every inbound Telegram message → classify intent → route to Coach or Ops or answer directly
- **Owns:** Tone, quiet-mode enforcement, opinionated pushback, memory retrieval, brief/review composition
- **Does NOT own:** Any CRUD operations. Delegates.
- **Tools:** `memory.*`, `notify.*`, `goals.nudge_due()`

#### Coach
- **Model:** Qwen 2.5 32B (local, daily); Claude Sonnet (cloud, weekly review + plan adjustment)
- **Job:** Fitness (PPL prescription + progression), nutrition (kcal accounting + easy-meal suggestions), study accountability (CKA/CKAD hours), habit confrontation
- **Tools:** `gym.*`, `food.*`, `study.*`, `goals.*`, `memory.*`
- **Tone:** Coach-like, motivating, opinionated ("Let's crush today" energy)

#### Ops
- **Model:** Qwen 2.5 7B (local, deterministic extraction); fallback to 14B on ambiguity
- **Job:** Calendar reads/writes-with-confirmation, expense CRUD, bill reminders, task/reminder CRUD, family-calendar merge
- **Tools:** `calendar.*`, `finance.*`, `bills.*`, `tasks.*`
- **Tone:** Factual, efficient, no personality

### 6.2 Hand-off Protocol
1. Orchestrator emits a `Task` object: `{intent, entities, target_agent, needs_cloud: bool}`
2. Target agent executes, returns `Result`
3. Orchestrator composes final Telegram message (applies tone)
4. All hand-offs logged in `agent_audit` for later prompt tuning

### 6.3 Memory Model (Three Tiers)

1. **Structured memory** — Postgres tables. Facts. Never LLM-summarized. Source of truth.
2. **Episodic memory** — Evening reviews, journal, decisions. Stored raw + embedded in pgvector. Retrieved by similarity for briefs and coaching.
3. **Semantic memory** — Long-lived facts about user (preferences, patterns, "prefers oats over eggs"). Extracted by Coach after evening review, stored in `user_facts` with confidence + source. Reviewed by user monthly ("confirm facts" flow).

**No fine-tuning, ever.** Facts live in DB, not model weights.

---

## 7. Database Schema (V1 Core Tables)

All names in English. PII flagged. Full DDL in separate file.

### 7.1 Identity & Config
- `user` — single row (id, name, tz, locale, quiet_until, tone_profile)
- `household_member` — wife, Martina, Jacob (id, relation, name **PII**, dob **PII**, notes **PII**)

### 7.2 Goals
- `goal` — id, kind (deadline|trajectory|frequency), title, target_value, target_date, cadence, status
- `goal_progress` — goal_id, ts, value, note
- `goal_checkin_policy` — goal_id, rule_json (e.g., "if 3-day gap → confront")

### 7.3 Calendar
- `calendar_source` — id, provider (google), account_label (personal|family), oauth_ref
- `calendar_event` — id, source_id, external_id, start, end, title, location, attendees, visibility (self|family|shared)
- `travel_plan` — event_id, mode (train|car), depart_at, arrive_at

### 7.4 Tasks & Reminders
- `task` — id, title, due_at, priority, status, source (user|system), goal_id
- `reminder` — id, target (task|bill|event), remind_at, channel

### 7.5 Finance
- `expense` — id, ts, amount_pln, category_id, merchant, note, raw_text
- `expense_category` — id, name (mortgage, groceries, kids, subscriptions, fuel, insurance, savings, clothes, events, gadgets, other), monthly_budget
- `bill` — id, name, amount_pln, due_day, recurrence (monthly|yearly), next_due, reminder_days_before (default 1)
- `savings_bucket` — id, name ("Harley"), target_amount, target_date, current_amount

### 7.6 Fitness
- `workout_template` — id, name ("PPL-Push"), exercises_json
- `workout_session` — id, ts, template_id, notes, rpe, session_type (gym|squash)
- `set_log` — session_id, exercise, set_num, weight_kg, reps, rir
- `progression_rule` — exercise, rule_json (e.g., "if 3x8@RIR2 completed → +2.5 kg")

### 7.7 Health
- `metric_daily` — date, weight_kg, resting_hr, sleep_hours, hrv, steps (nullable, Apple Watch source V2)

### 7.8 Nutrition
- `meal_log` — id, ts, meal_type, description_raw, est_kcal, est_protein_g, est_carbs_g, est_fat_g, confirmed_bool
- `daily_nutrition` — date, kcal_target, kcal_actual, protein_actual

### 7.9 Study
- `study_topic` — id, cert (CKA|CKAD), topic, target_hours, done_hours
- `study_session` — id, ts, topic_id, minutes, note

### 7.10 Family Time
- `family_event` — id, ts, kind (wife_evening|kids_activity|family_outing), participants, note

### 7.11 Memory
- `journal_entry` — id, ts, text **PII local-only**, embedding vector(1024)
- `user_fact` — id, key, value, confidence, source_journal_id, confirmed_bool, created_at
- `interaction_log` — id, ts, direction (in|out), channel, agent, tokens_local, tokens_cloud, redaction_applied

### 7.12 System
- `notification_policy` — id, event_key, channel, quiet_hours_json
- `agent_audit` — id, ts, agent, prompt_hash, tool_calls_json, result_summary

**Design note:** All timestamps `timestamptz`, all money `numeric(12,2) PLN`, all durations in minutes (int). No magic strings — enums in dedicated small tables.

---

## 8. MCP Tool Catalog

Each tool = one MCP server exposing typed methods.

### 8.1 `calendar` MCP
- `list_events(from, to, source?)`
- `find_conflicts(from, to)`
- `propose_event(event)` → returns draft, requires user confirm
- `create_event(event, confirmation_token)`
- `next_free_slot(duration_min, constraints)`

### 8.2 `finance` MCP
- `log_expense(raw_text)` → LLM-extracted + category guess + confirm
- `list_expenses(from, to, category?)`
- `month_summary(month)` → aggregates
- `upcoming_bills(days_ahead=14)`
- `savings_progress(bucket)`
- `budget_status(category, month)`

### 8.3 `gym` MCP
- `prescribe_today(template_rotation)` → next PPL day + weights per progression rule
- `log_session(feedback_text)` → parse + persist
- `progression_report(exercise, weeks=8)`
- `volume_last_week()`

### 8.4 `food` MCP
- `log_meal(raw_text)` → estimate kcal/macros, confirm
- `daily_total(date)`
- `suggest_easy_meal(constraints)` — e.g., "high protein, 20 min, ingredients I mentioned"
- `set_daily_target(kcal, protein_g)`

### 8.5 `study` MCP
- `log_session(cert, topic, minutes, note)`
- `week_hours(cert)`
- `next_topic(cert)` — from Mumshad curriculum ordering
- `variance_from_target(cert, weeks=4)`

### 8.6 `goals` MCP
- `list_active()`
- `progress(goal_id)`
- `nudge_due()` — returns goals overdue for check-in per policy

### 8.7 `memory` MCP
- `remember(text, tags?)`
- `recall(query, k=5)` — vector search
- `extract_facts(journal_id)` → proposed `user_fact` rows
- `confirm_fact(fact_id, keep|reject)`

### 8.8 `family` MCP
- `next_wife_evening_slot()`
- `weekly_family_report()`
- `kids_schedule(date)` — hardcoded 08:00–15:00 nursery

### 8.9 `notify` MCP
- `send_telegram(text, urgency)`
- `set_quiet(until)`
- `is_quiet()`

---

## 9. Notification & Scheduling Matrix

### 9.1 Scheduled (n8n cron)

| Time | Job | Owner | Notes |
|------|-----|-------|-------|
| 06:45 (dynamic if earlier calendar event) | Morning brief | Orchestrator | Calendar-aware; if 07:00 squash → 06:30 brief |
| 12:30 | Kcal check-in (only if under-logged) | Coach | Conditional |
| 17:30 | Gym prescription push if today = gym day | Coach | Push before session |
| 21:00 | Evening review (2 min, 5–7 Q) | Orchestrator | Always fires, even in quiet mode |
| 08:00 D-1 | Bill reminders (bills with `next_due <= tomorrow`) | Ops | 1 day before due date |
| Sun 20:00 | Weekly report | Coach + Ops + Orchestrator | All domains |
| 1st of month 20:00 | Monthly report | All | Trends, Harley savings, weight, recommendations |

### 9.2 Event-Triggered

| Event | Action | Agent | Notes |
|-------|--------|-------|-------|
| New calendar conflict detected | Immediate Telegram | Ops | Non-suppressible |
| Expense category >80% monthly budget | Immediate Telegram | Ops | Alert at threshold |
| Overspend >30% mid-month | Immediate Telegram + suggest cuts | Ops | Per user F2 answer |
| Skipped gym 5 days | Evening confrontation (honest + adjust plan) | Coach | Per user F1 answer (B+D) |
| Weight not logged in 7 days | Gentle nudge | Coach | |
| Study 0 hrs in last 3 days | Evening confrontation | Coach | |

### 9.3 Quiet Mode
- **Trigger phrases:** "shut up", "cisza", "not now", "quiet"
- **Suppression:** All non-emergency pushes until 21:00 evening review
- **Emergency exception:** Calendar event starting in <30 min that user would miss
- **Reset:** Evening review at 21:00 always fires

### 9.4 Refusal / Pushback
Coach challenges when:
- Kcal log >4000 or <1200 → "Confirm?"
- Weight change >2 kg in 1 week → "Confirm?"
- Expense >2000 PLN → "Confirm category?"
- Skipping gym reason = "tired" 3rd time in a row → "Tired or avoiding? Be honest."

---

## 10. Workout Template (PPL 4-Day Rotation)

Default program, stored in `workout_template` table, progressed by simple rules.

### 10.1 Template Structure

**Rotation:** Push → Pull → Legs → Rest (repeat)

#### Push Day
1. Bench Press 3x8 RIR 2
2. Overhead Press 3x8 RIR 2
3. Incline Dumbbell Press 3x10 RIR 2
4. Lateral Raises 3x12 RIR 2
5. Tricep Pushdowns 3x12 RIR 2

#### Pull Day
1. Deadlift 3x8 RIR 2
2. Pull-Ups 3x8 RIR 2 (or Lat Pulldown)
3. Barbell Row 3x8 RIR 2
4. Face Pulls 3x15 RIR 2
5. Bicep Curls 3x12 RIR 2

#### Legs Day
1. Squat 3x8 RIR 2
2. Romanian Deadlift 3x10 RIR 2
3. Leg Press 3x12 RIR 2
4. Leg Curl 3x12 RIR 2
5. Calf Raises 3x15 RIR 2

### 10.2 Progression Rules (Stored in `progression_rule`)

**Rule:** If all sets completed at target reps with RIR 2 → increase weight by:
- Compound lifts (squat, bench, deadlift, row, OHP): +2.5 kg
- Accessory lifts: +1–2 kg
- Bodyweight (pull-ups): add reps or weight vest

**Deload:** Every 6 weeks, reduce all weights by 10% for one week, then resume.

**User feedback ingestion:** After session, user sends one Telegram message: "Push done, bench felt good, OHP hard." Coach logs session, applies progression if criteria met.

---

## 11. Implementation Roadmap (6 Weeks)

### Week 1 — Foundation, No AI
**Goal:** Infrastructure works, Telegram echo bot live.

**Tasks:**
- Docker Compose: Postgres + pgvector, Redis, n8n, FastAPI skeleton
- Cloudflare Tunnel setup + Telegram Bot registration
- DB schema created + Alembic migrations
- Telegram echo bot working end-to-end
- GitHub repo initialized (private, personal account)

**User milestone:** You can DM the bot and it replies "hi Michał."

**Deliverables:**
- `docker-compose.yml`
- `alembic/` migrations
- `app/` FastAPI skeleton
- `.env.example`
- Telegram bot token configured

---

### Week 2 — Ops Agent + Calendar + Expenses
**Goal:** You log expenses daily; bill reminders arrive; calendar synced.

**Tasks:**
- Google OAuth for personal + family calendar
- Calendar sync into `calendar_event` table
- `finance` MCP: expense logging conversational (Qwen 2.5 7B extraction)
- `bills` table seeded (user to provide list later, placeholder for now)
- Bill reminder cron in n8n (08:00 D-1)
- Ops agent: routes expense/calendar commands

**User milestone:** You log "47 pln biedronka" via Telegram; it saves. Bill reminders work.

**Deliverables:**
- `mcp/finance.py`
- `mcp/calendar.py`
- `agents/ops.py`
- n8n workflow: bill reminder cron
- OAuth flow for Google Calendar

---

### Week 3 — Coach Agent + Gym + Food + Study
**Goal:** End-of-week you have real gym/food/study data.

**Tasks:**
- PPL template + progression rules seeded
- Gym prescription push before session (17:30 if gym day)
- One-message feedback ingestion after gym
- Meal logging with kcal estimation (Qwen 2.5 7B)
- Study session logging + weekly target vs. actual
- Coach agent: routes gym/food/study commands

**User milestone:** You complete a gym session, log it, and see progression applied. You log meals and see daily kcal total.

**Deliverables:**
- `mcp/gym.py`
- `mcp/food.py`
- `mcp/study.py`
- `agents/coach.py`
- `data/workout_templates.json` (PPL seeded)

---

### Week 4 — Orchestrator + Briefs + Reviews
**Goal:** Full daily loop works. You'd notice if it broke.

**Tasks:**
- Morning brief composer (dynamic time from calendar, Qwen 2.5 32B)
- Evening review flow (5–7 Q, 2 min, Orchestrator-led)
- Quiet mode + pushback logic
- Journal → embedding → memory (pgvector)
- Orchestrator agent: routes all, composes briefs
- n8n workflows: morning brief cron (06:45), evening review cron (21:00)

**User milestone:** You receive morning brief at 06:45, evening review at 21:00. Quiet mode works.

**Deliverables:**
- `agents/orchestrator.py`
- `mcp/memory.py`
- n8n workflows: morning brief, evening review
- Quiet mode logic in `notify` MCP

---

### Week 5 — Weekly/Monthly Reports + Goals Engine
**Goal:** First useful weekly report you actually read.

**Tasks:**
- Weekly report Sunday 20:00 (all domains, Claude Sonnet)
- Monthly report 1st 20:00 (trends, Harley savings, weight, recommendations)
- Goal check-in policies firing correctly
- Harley savings bucket tracking
- Fact extraction from journals → confirm flow
- n8n workflows: weekly report cron, monthly report cron

**User milestone:** Sunday 20:00 you get a report that's actually insightful. You confirm/reject extracted facts.

**Deliverables:**
- `mcp/goals.py`
- `agents/coach.py` (extended for weekly/monthly reports)
- n8n workflows: weekly report, monthly report
- Fact extraction + confirmation UI (Telegram inline buttons)

---

### Week 6 — Hardening, Audit, Iterate
**Goal:** Decide V2 scope from real data.

**Tasks:**
- `agent_audit` simple web UI (localhost, read-only)
- Backup script (Postgres dump to external drive, manual trigger)
- Prompt tuning based on 5 weeks of `interaction_log`
- Kill any feature you didn't use in weeks 1–5 (ruthless)
- Redaction Gateway unit tests
- Load testing (1 day of heavy Telegram usage)

**User milestone:** System feels stable. You have 5 weeks of data to review.

**Deliverables:**
- `scripts/backup.sh`
- `admin/audit_ui.py` (simple Flask app)
- Prompt refinement commits
- Test suite for Redaction Gateway
- V2 backlog prioritized

---

## 12. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Evening review feels like chore by week 3 | User stops using, system dies | High | Keep <90 sec, skip questions when data captured intra-day, always end with one positive |
| Coach confronts too early, feels annoying | User disables notifications | Medium | 2-week grace period, confrontation only after enough data |
| Windows + Docker Desktop + Ollama on gaming PC = GPU contention | Latency spikes, user frustration | Medium | Ollama pin to CPU for routing model; heavy models unload when idle; monitor GPU % in Docker stats |
| CKA/CKAD deadline Nov 30 conflicts with build timeline | Build incomplete OR certs failed | Medium | 6-week build ending late Oct leaves ~4 weeks for cert cram. Assistant helps study but cannot replace study time. |
| Kids' schema PII without disk encryption | Data breach if PC stolen/compromised | Low (home PC) | Flag for user: enable BitLocker (Windows) or accept risk |
| No backups until week 6 | Disk failure in weeks 4–5 loses everything | Low | User accepted. Schema backup-ready from day 1. Manual dump script in week 6. |
| Telegram bot token leak | Unauthorized access to assistant | Low | Store in `.env`, never commit, rotate if exposed |
| Cloud model cost spirals | Budget overrun | Low | Monitor `interaction_log` weekly, cap at $20/month with alert |

---

## 13. Success Metrics (Week 8 Evaluation)

At end of week 8, evaluate:

1. **Morning briefs read:** ≥80% read within 60 min of send
2. **Evening reviews completed:** ≥5 per week (out of 7)
3. **Gym sessions logged:** ≥90% same day
4. **Expenses logged:** ≥80% same evening
5. **CKA/CKAD study hours tracked:** Weekly variance <20% from target
6. **User self-report:** "I would be worse off without this" — ✅ or ❌

**Binary decision:** If ≥5 of 6 metrics pass → V2. If <5 → post-mortem, tear down or pivot.

---

## 14. Open Items (Blockers Before Week 1 Start)

1. **Current exact weight today** (to anchor 105→90 kg trajectory)
2. **Recurring bills list** (name, PLN, due day) — seed `bill` table week 2
3. **Google Calendar creation** (2 calendars: "Personal" + "Family" under Michał's account)
4. **BitLocker enablement** (user to confirm or accept risk)
5. **GitHub repo name** (suggestion: `personal-life-os`, private, personal account)
6. **Jira/project board decision** (answer below)

---

## 15. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-19 | Michał Zawadzki + Claude | Initial locked spec for V1 |

---

**End of Master Specification v1.0**
