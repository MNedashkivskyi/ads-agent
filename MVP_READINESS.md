# AdCopilot — MVP Readiness Assessment

> **Date:** April 2026  
> **Product:** AI-powered Google Ads assistant that detects campaign issues, surfaces recommendations via a Telegram bot, and executes approved changes automatically.

---

## Summary

The backend is further along than most early-stage projects. Core architecture, the full detection engine, Telegram bot, Google Ads read integration, billing, and auth are all production-grade. The main blocker to MVP is an **executor gap**: 6 out of 10 recommendation kinds will throw a runtime error if a user presses Approve. Three of those need real Google Ads mutations built; three should be marked informational-only with no Approve button.

**Current completion estimate: ~75% of MVP.**

---

## What Is Already Built

### Architecture & Infrastructure
- Hexagonal (ports & adapters) architecture — clean separation of domain, application, infrastructure, and interfaces layers
- PostgreSQL 16 + SQLAlchemy 2 async + Alembic (11 migrations covering the full schema)
- Celery + Redis for background task scheduling
- Docker Compose orchestration (dev setup)
- GitHub Actions CI (lint, type-check, unit tests)
- Structured logging via `structlog`, per-request ID middleware

### Detection Engine — 10/10 Rules Complete

All 10 rules are fully implemented and produce typed `Recommendation` objects with severity, evidence, and estimated savings:

| # | Rule | Recommendation Kind | Severity |
|---|------|---------------------|----------|
| 1 | Wasted search term (spend, 0 conversions) | ADD_NEGATIVE_KEYWORD | HIGH |
| 2 | Zero-conversion keyword (30+ clicks, cost > 2× CPA) | PAUSE_KEYWORD | HIGH |
| 3 | Low Quality Score (QS ≤ 4, cost > threshold) | PAUSE_KEYWORD | MEDIUM |
| 4 | Disapproved ad | FIX_DISAPPROVED_AD | CRITICAL |
| 5 | Broad match bleeding (30%+ unrelated impressions) | CHANGE_MATCH_TYPE | MEDIUM |
| 6 | No conversion tracking (100M+ micros, 0 conversions) | ENABLE_CONVERSION_TRACKING | CRITICAL |
| 7 | Budget capped (hitting daily cap, ROAS ≥ 1.0) | INCREASE_BUDGET | HIGH |
| 8 | Single ad in group (1 enabled ad, 100+ impressions) | ADD_AD_VARIATION | LOW |
| 9 | Dead keyword (0 impressions in 30 days) | PAUSE_KEYWORD | LOW |
| 10 | Wrong bidding strategy (30+ conversions on MAXIMIZE_CLICKS) | ADJUST_BIDDING_STRATEGY | MEDIUM |

### Telegram Bot — Complete
- Commands: `/start` (account linking via JWT deep-link), `/status`, `/history`, `/pause`, `/resume`, `/undo`, `/help`
- Inline buttons per recommendation: **Approve**, **Decline**, **Snooze**, **More** (shows evidence)
- Undo flow: `/undo` lists last 7 days of executed recommendations with Undo buttons
- Daily digest: top-5 recommendations sorted by severity and estimated savings, sent at 9 AM
- Security: user ownership validated on every callback; no cross-user access possible

### Google Ads Integration
- OAuth 2.0 flow: `/oauth/google/start` → Google → `/oauth/google/callback` → encrypted token storage
- Full read API: campaigns, ad groups, keywords, search terms, ads (snapshots stored in DB)
- Mutations implemented (write API): `pause_keyword`, `pause_ad`, `add_negative_keyword`, `update_campaign_budget` — plus reversal mutations for undo (`enable_keyword`, `enable_ad`, `remove_negative_keyword`)

### User Auth & Billing
- JWT authentication (signup + login with bcrypt)
- Stripe integration: 14-day trial checkout, customer portal, full webhook lifecycle (created → active → past_due → canceled)
- Plan tiers with Google Ads account limits: Starter (1), Growth (3), Pro (10)
- Telegram notification on payment failure and trial expiry (day-12 reminder)

### Scheduled Background Tasks
- **Nightly snapshots** — pulls full account data for all active accounts at midnight
- **Daily digest** — sends top-5 pending recommendations per user at 9 AM
- **Trial reminder** — notifies users on day 12 of trial
- **execute_recommendation_task** — runs on demand when user presses Approve

### LLM (Claude) Integration
- `ExplainRecommendationUseCase` generates natural-language explanations using the Anthropic SDK, with template fallback if the LLM is unavailable

### Web Frontend (Separate Repo)
- Lives in the `approve-ads-agent` GitHub repository
- Handles the onboarding flow (sign-up, Google Ads OAuth connect)
- Backend OAuth endpoints (`/oauth/google/start`, `/oauth/google/callback`) are implemented and waiting

---

## Gaps — What Is Still Needed for MVP

### 1. Executor Gap — CRITICAL BLOCKER

When a user presses Approve on a recommendation, the system routes to a registered executor by `RecommendationKind`. Only 4 of 10 kinds have executors. The other 6 will raise `ValueError: No executor registered for [KIND]` at runtime.

**File:** `adcopilot/application/use_cases/execute_recommendation.py` (line ~71)  
**File:** `adcopilot/application/use_cases/undo_recommendation.py` (line ~163)

#### Group A — Must Build Executors + Google Ads Mutations (3 kinds)

These are fully automatable via the Google Ads API:

| Kind | What the executor must do | Google Ads API operation |
|------|--------------------------|--------------------------|
| CHANGE_MATCH_TYPE | Update keyword match type (broad → phrase or exact) | `MutateAdGroupCriteriaRequest` with updated `match_type` |
| ADJUST_BIDDING_STRATEGY | Switch campaign bidding strategy to `MAXIMIZE_CONVERSIONS` | `MutateCampaignsRequest` with updated `bidding_strategy_type` |
| ADJUST_BUDGET | Change campaign daily budget by a specified amount | Already partially covered by `update_campaign_budget`; needs a dedicated executor wired to this kind |

**Work required:**
- Add `change_match_type` and `adjust_bidding_strategy` methods to `adcopilot/infrastructure/google_ads/mutations_adapter.py`
- Add corresponding fake implementations to `adcopilot/infrastructure/google_ads/fake_mutations.py`
- Add `GoogleAdsMutationsPort` method signatures to `adcopilot/application/ports/google_ads_mutations.py`
- Create executor classes in `adcopilot/application/executors/`
- Register them in `execute_recommendation.py` `_default_executors()`
- Add undo logic in `undo_recommendation.py`

#### Group B — Mark as Informational-Only, Hide Approve Button (3 kinds)

These require human action outside the system's control. Auto-execution is not planned.

| Kind | Why not auto-executable | What to show the user |
|------|------------------------|----------------------|
| FIX_DISAPPROVED_AD | Ad disapproval reasons vary; fix requires editing ad copy, which needs human judgment | Show recommendation + evidence + link to Google Ads UI; no Approve button |
| ADD_AD_VARIATION | Writing a new ad requires creative input | Same — informational card only |
| ENABLE_CONVERSION_TRACKING | Requires installing a tag on the advertiser's website | Same — informational card + setup guide link |

**Work required:**
- Add a `is_executable` flag or check in `adcopilot/infrastructure/telegram/digest_notifier.py` and `adcopilot/infrastructure/telegram/callback_handler.py` — suppress the Approve button for these 3 kinds
- Alternatively, add these kinds to a `NON_EXECUTABLE_KINDS` set in the domain and check it before rendering buttons
- These recommendations should still appear in the daily digest but as advisory cards

### 2. Telegram Webhook Mode for Production — SHOULD-HAVE

`scripts/run_bot.py` runs the bot in polling mode, which is fine for local development but **not suitable for production** (polling does not scale, has higher latency, and is fragile).

The webhook endpoint already exists at `adcopilot/interfaces/api/telegram.py`.

**Work required:**
- Configure the Telegram bot to register the webhook URL on startup (call `setWebhook` via the Bot API during FastAPI lifespan)
- Remove or gate the polling script behind a `DEV_MODE` flag
- Update `adcopilot/infrastructure/telegram/bot.py` to support webhook-only mode in production

### 3. Failed Execution Notification — SHOULD-HAVE

When `execute_recommendation_task` runs and the executor fails (raises an exception or returns a FAILED status), the user currently receives no feedback. The recommendation silently transitions to FAILED in the database.

**File:** `adcopilot/interfaces/worker/tasks.py` — `execute_recommendation_task`

**Work required:**
- After catching an execution error, call `telegram_notifier.send_execution_failed(user, recommendation, error_message)`
- Add a `send_execution_failed` method to `adcopilot/application/ports/telegram_notifier.py` and implement it in `adcopilot/infrastructure/telegram/digest_notifier.py`

### 4. OAuth Token Refresh Validation — SHOULD-HAVE

The `GoogleAdsAccountModel` has a `needs_reauth` flag, but it is unclear whether the token refresh path is fully exercised end-to-end during snapshot and execution tasks. An expired access token at execution time would silently fail or produce a confusing error.

**File:** `adcopilot/infrastructure/google_ads/client.py`  
**File:** `adcopilot/infrastructure/db/repositories/oauth_credentials_repository.py`

**Work required:**
- Verify (and write an integration test for) the token refresh flow: access token expired → use refresh token → get new access token → retry operation
- Confirm the `needs_reauth` flag is set correctly when the refresh token itself is invalid (e.g., user revoked access)
- Ensure the user receives a Telegram notification asking to re-authenticate when `needs_reauth` is set

### 5. Production Deployment Config — SHOULD-HAVE

The current `docker-compose.yml` is development-oriented: no TLS termination, no resource limits, no restart policies beyond `unless-stopped`, and secrets managed via a plain `.env` file.

**Work required:**
- Add a `docker-compose.prod.yml` override with:
  - Reverse proxy (nginx or Caddy) with automatic HTTPS
  - Resource limits (`mem_limit`, `cpus`) on all services
  - Production-grade Celery concurrency settings
- Document secret management approach (e.g., Docker secrets, environment injection from a secrets manager)
- Add a `DEPLOYMENT.md` or section to README covering production setup steps

### 6. Rate Limiting on Auth Endpoints — SHOULD-HAVE

`POST /api/auth/signup` and `POST /api/auth/login` have no rate limiting, making them vulnerable to brute-force attacks.

**File:** `adcopilot/interfaces/api/auth.py`

**Work required:**
- Add slowapi or a similar rate-limiting middleware
- Limit login attempts to ~5 per minute per IP

### 7. Frontend ↔ Backend Integration Verification — MUST-HAVE

The `approve-ads-agent` frontend repo handles onboarding, but the integration with this backend has not been verified end-to-end in this codebase. Before MVP:

- Confirm CORS settings in `adcopilot/main.py` allow the frontend domain
- Confirm the Stripe `PRICE_ID` values in `.env.example` match the frontend's plan selection UI
- Test the full user journey: sign up → connect Google Ads → receive first digest → approve recommendation → see change in Google Ads

---

## Post-MVP (Nice-to-Have)

| Item | Notes |
|------|-------|
| Monitoring & alerting | Sentry for error tracking; Prometheus + Grafana for metrics |
| Multi-language support | `User.language` field exists but no i18n implementation |
| Web dashboard | Recommendation history, account health overview |
| Load testing | Verify Celery worker throughput under concurrent accounts |
| Snapshot diff alerts | Notify user when a key metric changes significantly day-over-day |
| More detection rules | Ad scheduling gaps, landing page speed issues, audience bid adjustments |

---

## Recommended Next Steps (Priority Order)

1. **Hide Approve button** for `FIX_DISAPPROVED_AD`, `ADD_AD_VARIATION`, `ENABLE_CONVERSION_TRACKING` — 1–2 hours, prevents runtime crashes for CRITICAL and LOW severity recommendations that are already being generated today
2. **Build 3 missing executors** (`CHANGE_MATCH_TYPE`, `ADJUST_BIDDING_STRATEGY`, `ADJUST_BUDGET`) — 1–2 days per executor including mutations, tests, and undo logic
3. **Verify OAuth token refresh end-to-end** — 0.5 days
4. **Switch Telegram bot to webhook mode** — 0.5 days
5. **Add failed-execution user notification** — 0.5 days
6. **End-to-end integration test** with the frontend repo — 1 day
7. **Production deployment config** — 1 day
