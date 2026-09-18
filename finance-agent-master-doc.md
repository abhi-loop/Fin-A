# Intelligent Financial Decision Agent — Master Document

**Status:** Living doc — update as scope changes during the 12-hour build.
**Last updated:** 2026-09-18

---

## 1. Problem Statement (locked)

A chat-based agent that answers "Should I buy/invest/spend on X?", logs expenses conversationally, tracks budgets/goals, and gives reasoned, confidence-scored financial recommendations.

---

## 2. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                            FRONTEND                                │
│         Chat UI (single input) + Dashboard (budget/goals)          │
│                     Auth: Supabase JS client                       │
└───────────────────────────────┬────────────────────────────────────┘
                                 │ HTTPS + JWT (Supabase session)
┌───────────────────────────────▼────────────────────────────────────┐
│                         BACKEND (FastAPI)                           │
│  - Verifies JWT on every request                                    │
│  - All DB access scoped to authenticated user_id                    │
└───────────────────────────────┬────────────────────────────────────┘
                                 │
┌───────────────────────────────▼────────────────────────────────────┐
│                        INTENT ROUTER (LLM call #1)                  │
│   Classifies message into:                                          │
│   expense_log | budget_query | investment_query | goal_planning     │
│   | ipo_alert | out_of_scope_domain                                 │
└─────────────┬────────────────────────────────────┬──────────────────┘
              │                                     │
   ┌──────────▼──────────┐              ┌───────────▼───────────────┐
   │  STRUCTURED PATH      │              │      AGENTIC PATH           │
   │  (no LLM reasoning,   │              │  (tool-calling loop)         │
   │   deterministic)      │              │                              │
   │                        │              │  Tools available:            │
   │  - Regex/small-model   │              │   1. get_user_profile()      │
   │    extraction: amount, │              │      → budget, goals, risk   │
   │    category, date      │              │        appetite (DB)         │
   │  - Direct DB write to  │              │   2. web_search()             │
   │    `expenses` table    │              │      → live price/IPO news    │
   │  - Recompute budget    │              │   3. get_spending_history()   │
   │    status              │              │      → recent category spend  │
   │  - Trigger alert if     │              │                              │
   │    over threshold      │              │  → Confidence Scorer          │
   └────────────────────────┘              │    (LLM call #2, structured   │
                                            │     JSON output: verdict,     │
                                            │     confidence %, reasoning,  │
                                            │     caveats)                  │
                                            └───────────┬────────────────┘
                                                          │
                                            ┌─────────────▼────────────┐
                                            │   RECOMMENDATION OBJECT     │
                                            │  { verdict, confidence,      │
                                            │    reasoning[], alert? }      │
                                            └─────────────┬────────────┘
                                                          │
┌─────────────────────────────────────────────────────────▼──────────┐
│                          DATA LAYER (Supabase / Postgres)            │
│  Tables: users(auth) | profiles | expenses | budgets | goals         │
│          | alerts | conversation_log                                 │
│  Security: Row Level Security (RLS) — every table scoped to auth.uid()│
└────────────────────────────────────────────────────────────────────┘
                                                          │
                                            ┌─────────────▼────────────┐
                                            │   ALERTS / NOTIFICATIONS   │
                                            │   In-app toast + stored    │
                                            │   alert row (mocked "push")│
                                            └────────────────────────────┘
```

---

## 3. Auth Layer (deliberately minimal)

- **Provider:** Supabase Auth (email/password + Google OAuth)
- **No custom JWT/session code.** Backend just verifies the Supabase-issued JWT on incoming requests.
- **PII/security story for judges:** Row Level Security policies (`user_id = auth.uid()`) on every table → a stolen API call still can't read another user's financial data. This is the one sentence to have ready.
- **Explicitly not building:** custom password hashing, OTP, refresh-token rotation, session store.

---

## 4. Domain Scope for the Demo

| Domain | Status |
|---|---|
| Expense logging + budget check | ✅ Full build |
| Stock investment decision | ✅ Full build (flagship demo) |
| IPO alert | ✅ Full build (reuses investment agent) |
| Goal/trip savings planning | 🟡 Stretch, build if time remains |
| Loans / insurance / travel / career | ⚪ Router recognizes intent, replies "coming soon" — not built |

---

## 5. Implementation Plan (12-hour budget)

### Hour 0–0.5 — Project setup
- [ ] Create Supabase project, enable email + Google auth
- [ ] Define schema: `profiles`, `expenses`, `budgets`, `goals`, `alerts`
- [ ] Enable RLS on all tables, write policies (`auth.uid() = user_id`)
- [ ] Scaffold FastAPI backend + repo, scaffold frontend (Next.js/React)
- [ ] Wire Supabase auth client in frontend, protect routes

### Hour 0.5–1 — Auth wiring end-to-end
- [ ] Login/signup screens (Supabase prebuilt UI or minimal custom form)
- [ ] Backend middleware: verify JWT, extract `user_id`, reject if invalid
- [ ] Smoke test: logged-in user hits a protected `/me` endpoint

### Hour 1–2.5 — Structured path (expense logging)
- [ ] Extraction function: parse "I spent 500 on fuel today" → `{amount, category, date}` (start with a lightweight LLM prompt returning strict JSON, fallback regex for numbers)
- [ ] POST `/expenses` → writes row, recomputes month-to-date spend per category
- [ ] Budget comparison logic: category spend vs `budgets` table
- [ ] Response templating: "You've spent ₹X of ₹Y budget in [category]"
- [ ] Alert trigger: if spend > budget → insert row into `alerts`, return in response

### Hour 2.5–3 — Intent router
- [ ] Single LLM call, strict JSON output: `{intent, extracted_entities}`
- [ ] Route table: intent → handler function
- [ ] Fallback: unknown/out-of-scope domain → friendly "not supported yet" response (covers loans/insurance/travel/career without building them)

### Hour 3–6 — Agentic investment path (flagship feature)
- [ ] Tool: `get_user_profile()` — pulls budget headroom, existing goals, stated risk tolerance from DB
- [ ] Tool: `web_search()` — live price lookup (stock ticker, or IPO news)
- [ ] Tool: `get_spending_history()` — recent discretionary spend, so recommendation accounts for cash flow, not just balance
- [ ] Confidence scorer prompt — LLM call #2, forced JSON output:
  ```json
  {
    "verdict": "buy | hold | avoid | insufficient_funds",
    "confidence": 0-100,
    "reasoning": ["point 1", "point 2", "point 3"],
    "caveats": ["..."]
  }
  ```
- [ ] Wire tool-calling loop (Claude/OpenAI function calling) with the 3 tools above
- [ ] Test with sample prompts: Apple stock ₹5000, IPO subscription

### Hour 6–7 — Alerts (mocked "real-time push")
- [ ] `alerts` table: type (budget_overrun | ipo | goal_milestone), message, read/unread
- [ ] Frontend: poll or Supabase realtime subscription → toast notification
- [ ] Explicitly scope down: no FCM/APNs, no email — in-app only, call it out as "roadmap: real push via FCM" in pitch

### Hour 7–9 — Frontend polish
- [ ] Chat interface wired to backend
- [ ] Budget/goals dashboard (simple bar charts: spent vs budget per category)
- [ ] Recommendation card UI: verdict badge + confidence % + reasoning bullets (this sells the "intelligence" visually)
- [ ] Alert toast component

### Hour 9–10.5 — Stretch: goal planning
- [ ] `goals` table: target amount, target date, current saved
- [ ] Simple monthly-contribution-needed calculation
- [ ] "Should I book this flight" → checks against goal/budget headroom, reuses confidence scorer

### Hour 10.5–11.5 — Testing + demo script
- [ ] Walk all 5 sample prompts from problem statement end-to-end
- [ ] Seed demo account with realistic expense history (so budget/pattern analysis looks real, not empty)
- [ ] Write 2-minute demo script hitting: expense log → budget alert → stock decision → IPO alert

### Hour 11.5–12 — Pitch prep
- [ ] One slide: architecture diagram (this doc)
- [ ] One slide: "what we deliberately scoped out and why" (shows judgment, not just time pressure)
- [ ] Rehearse the auth/security one-liner

---

## 6. Judge-Defensibility Talking Points (keep handy)

- **Why not one giant LLM prompt for everything?** → Intent router + structured/agentic split. Deterministic ops (expense logging) don't hit an LLM twice; only genuine decisions do. Cheaper, faster, more reliable.
- **Why Supabase auth instead of custom?** → Security fundamentals (hashed passwords, JWT, RLS) shouldn't be hand-rolled in 12 hours; reuse battle-tested infra, spend the saved time on the actual agent.
- **How is financial data protected?** → RLS policies scope every row to `auth.uid()`; no query path can cross users even with a compromised endpoint.
- **What's the confidence score based on?** → Explicit structured reasoning: budget headroom, live market data, spending pattern — not a black-box number.
- **What's stubbed and why?** → Real push notifications (FCM/APNs) and 4 of the 6 domains are named explicitly as roadmap, not silently missing — shows scope discipline under time pressure.

---

## 7. Open Decisions (fill in as you go)

- [ ] LLM provider/model for router + confidence scorer:
- [ ] Web search API for live prices:
- [ ] Frontend framework: Next.js / plain React / other:
- [ ] Demo account seed data source:
