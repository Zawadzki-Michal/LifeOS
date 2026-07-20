# Personal Life OS — Handoff Document for Any Claude Instance

**Purpose:** This document allows any Claude instance (including future sessions) to pick up this project cold and understand the full context within 2 minutes.

**Status:** Active project, Week 0 (planning complete, implementation not started)  
**Created:** 2026-01-19  
**Owner:** Michał Zawadzki  

---

## What This Project Is

A **proactive AI accountability system** for a single user (Michał, 38, engineer, Kraków, wife + 2 kids). The system:
- Messages the user **first** (not reactive)
- Tracks progress across **gym, nutrition, finance, study, family time**
- Provides **opinionated coaching** and structured accountability
- Uses **hybrid local/cloud AI** (privacy-first, RTX 3090 local models + cloud for hard reasoning)
- **Telegram-only interface** in V1 (PWA/native later)

**Key differentiator vs. every other personal AI:** The assistant messages you on a schedule with structured check-ins and confronts you when you slip. It's not a chatbot. It's a coach + ops layer.

---

## Why This Exists

Michał tried ChatGPT health coaching and it worked well, **except** it didn't message him first. He's bad at self-initiated note-taking and list-making. He tends to:
- Overfocus on work, under-invest in family time
- Play games instead of studying for certs (CKA/CKAD due Nov 30)
- Skip gym when unmotivated
- Not track family finances

The system's job is to **reduce planning friction** and provide **behavior change through structured accountability**.

---

## V1 Goals (Locked)

By end of 6 weeks, the system must:
1. Send **morning brief at 06:45** (calendar-aware, weather, tasks, gym day, kcal target, meal suggestions)
2. Send **evening review at 21:00** (5–7 questions, 2 min, logs expenses/gym/food/reflections)
3. Send **weekly report Sunday 20:00** (finance, gym, food, study, family time)
4. Send **monthly report 1st 20:00** (trends, Harley savings progress, weight trend, recommendations)
5. Track **CKA/CKAD study hours** against target, confront if 3-day gap
6. Track **gym sessions** (2–3/week target), prescribe PPL workout before session, log after
7. Track **expenses** (conversational logging: "47 pln biedronka" → categorized → stored)
8. Track **nutrition** (kcal estimation, daily total vs. target 2300 kcal)
9. Track **family time** (1 wife evening/week, 1 kids activity/week)
10. **Remind bills** 1 day before due date
11. **Quiet mode** ("shut up" → suppresses until evening review)
12. **Opinionated pushback** ("6000 kcal? Are you sure?")

**Success metric (week 8):** User self-reports "I would be worse off without this." Binary pass/fail.

---

## V1 Non-Goals (Explicit Exclusions)

These are **not negotiable** for V1. Any feature request overlapping these gets deferred:
- ❌ Bank/PSD2 integration (manual entry only)
- ❌ Work task management (Jira/Zendesk out of scope)
- ❌ Work Google calendar (deferred to V1.5)
- ❌ Multi-user (wife/kids = context only)
- ❌ Native iOS app (PWA is V2, native V3+)
- ❌ Home automation, Siri/Alexa
- ❌ Photo food recognition, micronutrients
- ❌ Bespoke workout generation (template PPL only)
- ❌ Automated backups (schema backup-ready, automation V2)
- ❌ Voice in/out (V2)

---

## Architecture (High-Level)

```
Telegram (user)
   ↓ HTTPS webhook
Cloudflare Tunnel (no port forwarding)
   ↓
Windows PC (RTX 3090, Docker Desktop)
   ├─ n8n (cron, webhook, glue)
   ├─ FastAPI (Telegram adapter, API)
   ├─ LangGraph (3 agents: Orchestrator, Coach, Ops)
   ├─ Ollama (Qwen 2.5 7B/14B/32B local)
   ├─ OpenRouter (Claude Sonnet for hard reasoning)
   ├─ PostgreSQL + pgvector (source of truth)
   ├─ Redis (cache, session state, quiet mode flag)
   └─ MCP servers (calendar, finance, gym, food, study, goals, memory)
```

**Model allocation:**
- **Local (Qwen 2.5):** Intent classification, structured extraction, daily briefs
- **Cloud (Claude Sonnet):** Weekly/monthly analysis, coaching decisions, plan changes
- **Cost:** ~$5–15/month OpenRouter

**Privacy:**
- Kids' names/ages, wife name/calendar, journal entries = **never leave box**
- Finance transactions = raw OK to cloud (user confirmed)
- Health metrics = non-anonymized OK to cloud (user confirmed)
- Redaction Gateway middleware enforces per-domain policy

---

## Three Agents (Not Twelve)

User originally proposed 12 agents. We negotiated down to 3 for V1:

### 1. Orchestrator
- **Model:** Qwen 2.5 14B (local routing), Claude Sonnet (cloud planning)
- **Job:** Routes all messages, composes briefs/reviews, owns tone, enforces quiet mode, memory retrieval
- **Does NOT:** Any CRUD. Delegates to Coach/Ops.

### 2. Coach
- **Model:** Qwen 2.5 32B (local daily), Claude Sonnet (cloud weekly review)
- **Job:** Fitness (PPL prescription + progression), nutrition (kcal + meal suggestions), study (CKA/CKAD hours), habit confrontation
- **Tone:** Motivating, opinionated ("Let's crush today")

### 3. Ops
- **Model:** Qwen 2.5 7B (local extraction), fallback 14B
- **Job:** Calendar CRUD, expense logging, bill reminders, tasks
- **Tone:** Factual, efficient, no personality

**Everything else** (Analytics, Memory, Family) = **tools or cron jobs**, not agents.

---

## Goals (First-Class DB Entities)

Goals drive proactive behavior. Each has a target, cadence, check-in rule:

| Goal | Type | Target | Check-in Rule |
|------|------|--------|---------------|
| CKA cert | deadline | Pass by Nov 30 | 3-day study gap → confront |
| CKAD cert | deadline | Pass by Nov 30 (after CKA) | Same |
| Weight loss | trajectory | 105→90 kg @ 0.4 kg/week (~9 months) | Trend divergence → review |
| Harley savings | trajectory | 5–10k PLN own, rest loan (total 40k PLN) | Missed month → flag |
| Gym | frequency | 2–3/week | <2/week → confront |
| Squash | frequency | 2–3/week | Informational |
| Wife time | frequency | 1 evening/week | 0 last week → nudge |
| Kids activity | frequency | 1 weekend/week | Same |

---

## Database (Source of Truth)

PostgreSQL + pgvector. Key tables:
- **user, household_member** (identity, PII flagged)
- **goal, goal_progress, goal_checkin_policy** (first-class goals)
- **calendar_source, calendar_event, travel_plan** (calendar)
- **expense, expense_category, bill, savings_bucket** (finance)
- **workout_template, workout_session, set_log, progression_rule** (fitness)
- **metric_daily** (health: weight, HR, sleep, HRV, steps)
- **meal_log, daily_nutrition** (nutrition)
- **study_topic, study_session** (CKA/CKAD prep)
- **family_event** (wife time, kids activities)
- **journal_entry, user_fact, interaction_log** (memory)
- **notification_policy, agent_audit** (system)

All timestamps `timestamptz`, all money `numeric(12,2) PLN`, all durations in minutes (int).

---

## MCP Tools (Agent-Callable)

Each MCP server exposes typed methods:
- **calendar:** list_events, find_conflicts, propose_event, create_event, next_free_slot
- **finance:** log_expense, list_expenses, month_summary, upcoming_bills, savings_progress, budget_status
- **gym:** prescribe_today, log_session, progression_report, volume_last_week
- **food:** log_meal, daily_total, suggest_easy_meal, set_daily_target
- **study:** log_session, week_hours, next_topic, variance_from_target
- **goals:** list_active, progress, nudge_due
- **memory:** remember, recall (vector search), extract_facts, confirm_fact
- **family:** next_wife_evening_slot, weekly_family_report, kids_schedule
- **notify:** send_telegram, set_quiet, is_quiet

---

## Scheduled Events (n8n Cron)

| Time | Job | Agent |
|------|-----|-------|
| 06:45 (dynamic if earlier event) | Morning brief | Orchestrator |
| 12:30 | Kcal check-in (if under-logged) | Coach |
| 17:30 | Gym prescription (if gym day) | Coach |
| 21:00 | Evening review (always fires) | Orchestrator |
| 08:00 D-1 | Bill reminders | Ops |
| Sun 20:00 | Weekly report | All |
| 1st 20:00 | Monthly report | All |

**Event-triggered:**
- Calendar conflict → immediate
- Expense category >80% budget → immediate
- Overspend >30% mid-month → immediate + suggest cuts
- Skipped gym 5 days → evening confrontation
- Study 0 hrs in 3 days → evening confrontation

---

## Workout Template (PPL 4-Day Rotation)

**Rotation:** Push → Pull → Legs → Rest (repeat)

**Push:** Bench Press, OHP, Incline DB Press, Lateral Raises, Tricep Pushdowns (3x8-12)  
**Pull:** Deadlift, Pull-Ups, Barbell Row, Face Pulls, Bicep Curls (3x8-15)  
**Legs:** Squat, RDL, Leg Press, Leg Curl, Calf Raises (3x8-15)  

**Progression:** If all sets completed at target reps with RIR 2 → +2.5 kg (compounds), +1–2 kg (accessories)  
**Deload:** Every 6 weeks, -10% all weights for one week

**User ingestion:** One Telegram message after session: "Push done, bench felt good, OHP hard." Coach logs + applies progression.

---

## 6-Week Roadmap

| Week | Milestone | User Can Do |
|------|-----------|-------------|
| 1 | Infra + Telegram echo bot | DM bot, get reply "hi Michał" |
| 2 | Calendar + expenses | Log expenses, get bill reminders |
| 3 | Gym + food + study | Complete gym session, log meals, track study hours |
| 4 | Briefs + reviews | Get morning brief 06:45, evening review 21:00 |
| 5 | Weekly/monthly reports + goals | Get first useful weekly report Sunday 20:00 |
| 6 | Hardening + audit | System feels stable, 5 weeks of data |

---

## Household Context (PII)

- **Michał:** 38, engineer, Kraków, currently ~105 kg (to confirm), target 90 kg
- **Wife:** Name in DB (never sent to cloud), has Google Calendar (shared), Samsung/Google Calendar user
- **Martina:** 7 years old (PII, never sent to cloud)
- **Jacob:** 5 years old (PII, never sent to cloud)
- **Kids schedule:** Nursery 08:00–15:00 weekdays (hardcoded)

---

## Daily Routine (Drives Scheduling)

**Weekday WFH (Wed/Thu/Fri):**
- 06:30 wake, 06:45 **morning brief**, 07:00–08:00 kids/squash/gym, 09:00–17:00 work, 15:00 pick up kids, 17:30 **gym prescription**, 21:00 **evening review**, 22:30 sleep

**Weekday Office (Mon/Tue or Thu):**
- 06:30 wake, 06:45 **morning brief + travel reminder**, 07:40 train to Kraków, 09:00–17:00 office, 21:00 **evening review**, 22:30 sleep

**Weekend:**
- Similar wake/sleep, family activities, study time, gym/squash flexible, **Sun 20:00 weekly report**

---

## Tone & Language

- **Default language:** English (assistant writes English by default)
- **Input:** User can write Polish or English; system auto-detects and translates
- **Schema:** English only (categories, tags, field names)
- **Tone:** Coach-like, motivating, opinionated, uses "Michał" (not "Sir")
- **Quiet mode:** Suppresses all non-emergency until 21:00 evening review
- **Pushback:** "6000 kcal? Are you sure?" when data looks wrong

---

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL 16 + pgvector, Redis, Docker Desktop
- **AI:** Ollama (Qwen 2.5 7B/14B/32B local), OpenRouter (Claude Sonnet cloud)
- **Agents:** LangGraph (state machine)
- **Integrations:** n8n (cron, webhooks, glue)
- **Communication:** Telegram Bot API
- **Infra:** Cloudflare Tunnel (ingress), Windows PC (RTX 3090, 32GB RAM)
- **Version control:** GitHub (private, personal account)

---

## Open Items (Blockers Before Week 1)

1. **Current exact weight today** (to anchor 105→90 kg trajectory) — user to provide tomorrow
2. **Recurring bills list** (name, PLN, due day) — user to provide later
3. **Google Calendar creation** (2 calendars: "Personal" + "Family" under Michał's account) — week 1 task
4. **BitLocker enablement** (user to confirm or accept risk) — not sure yet
5. **GitHub repo name** (suggestion: `personal-life-os`, private) — answered below
6. **Jira/project board** (answered below)

---

## How to Use This Handoff

If you are a Claude instance picking this up:

1. **Read `00-MASTER_SPEC.md` first** (full design, locked V1 scope)
2. **Read this file** (quick context refresh)
3. **Ask user:** "What week are we in? What's the current task?"
4. **Check open items** (above) — if any blocker unresolved, ask before proceeding
5. **Follow the roadmap** (week-by-week milestones)
6. **Do NOT:** suggest features outside V1 scope (refer to non-goals list)
7. **Do NOT:** change agent count, add multi-user, add voice, add native app — all V2+

---

## Key Decisions (Why We Made Them)

- **3 agents, not 12:** Coordination overhead kills multi-agent systems. 3 agents + tools is simpler.
- **No fine-tuning:** Facts live in DB (structured + vector), not model weights. Models are stateless.
- **Hybrid local/cloud:** Privacy for PII, cloud for hard reasoning. Cost-effective (~$5–15/month).
- **Telegram-only V1:** Fastest to ship, lowest friction. PWA/native later.
- **PPL template, not bespoke generation:** Simpler, proven, user can customize later.
- **No work calendar V1:** Reduces scope, user already has OpenCode for work context.
- **Manual expense entry:** Bank integration is complex, high security risk, low V1 value.

---

## Common Pitfalls to Avoid

1. **Do not build features the user didn't use in previous week.** Kill ruthlessly in week 6.
2. **Do not make evening review >2 min.** User will stop doing it.
3. **Do not confront too early.** Need 2 weeks of data before habit confrontation.
4. **Do not send PII to cloud.** Redaction Gateway enforces, but double-check every payload.
5. **Do not add dependencies without asking.** User wants simplest stack possible.
6. **Do not optimize prematurely.** Build, test, iterate. Week 6 is for hardening.

---

## Success Looks Like (Week 8)

- User reads ≥80% of morning briefs within 60 min
- User completes ≥5 evening reviews/week
- User logs ≥90% of gym sessions same day
- User logs ≥80% of expenses same evening
- CKA/CKAD study hours tracked with <20% variance from target
- **User says:** "I would be worse off without this."

If ≥5 of 6 metrics pass → V2. If <5 → post-mortem, tear down or pivot.

---

**End of Handoff Document**

Next steps: Answer tooling questions (Jira/GitHub), then await user's "start Week 1" signal.
