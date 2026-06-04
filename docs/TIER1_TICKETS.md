# Tier-1 Implementation Tickets

Goal: close the four gaps that block "credible launch assistant → genuine agency replacement".
Each ticket follows the existing hexagonal pattern: **Protocol port** in `adcopilot/application/ports/`,
**adapter** in `adcopilot/infrastructure/google_ads/`, **fake** in `tests/` (see `fake_mutations.py`),
**use case** in `adcopilot/application/use_cases/`.

Epics:
- [EPIC A] Real keyword research (Keyword Planner)
- [EPIC B] Conversion-tracking bootstrap (create + validate)
- [EPIC C] Conversion-lag handling in detection rules
- [EPIC D] Ship the Telegram bot on main

---

## EPIC A — Real keyword research

Today keywords come only from LLM guesses + YAML templates (`generate_proposal.py` → `build_structure`,
`config/verticals/*.yaml`). No search volume, no competition, no real CPC. This epic adds
`KeywordPlanIdeaService` (Google Ads' Keyword Planner API — you already use `google-ads-python`).

### A1 — `KeywordPlannerPort` + value objects
- **New file:** `adcopilot/application/ports/keyword_planner.py`
- Define `@dataclass(frozen=True) KeywordIdea { text, avg_monthly_searches: int, competition: str ("LOW"/"MEDIUM"/"HIGH"), low_top_of_page_bid_micros: int, high_top_of_page_bid_micros: int }`
- Define `class KeywordPlannerPort(Protocol)`:
  - `async def keyword_ideas(self, refresh_token, customer_id, *, seed_keywords: list[str], seed_url: str | None, location: str, language: str = "pl") -> list[KeywordIdea]: ...`
  - Contract: never raises — returns `[]` on API error (mirror `ConversionTrackingChecker.check` docstring convention).
- **Acceptance:** port imports cleanly, no infra deps.

### A2 — Adapter against `KeywordPlanIdeaService`
- **New file:** `adcopilot/infrastructure/google_ads/keyword_planner_adapter.py`
- Use `client.get_service("KeywordPlanIdeaService").generate_keyword_ideas(...)`.
- Reuse the client factory in `infrastructure/google_ads/client.py` (same `refresh_token` pattern as `mutations_adapter.py`).
- Map Polish geo names → geo target constant IDs. **Reuse** the voivodeship/city mapping in
  `adcopilot/domain/polish_market/voivodeship_data.py`; language constant = Polish (`1045`).
- Wrap quota errors via the existing helper in `queries.py:63` (`"quota"/"resource exhausted"` → `GoogleAdsRateLimited`) — catch and return `[]` per the port contract.
- **Acceptance:** integration test (marked, skipped in CI without creds) returns ≥1 idea for seed `["fryzjer"]`, location `"Warszawa"`.

### A3 — Fake + unit tests
- **New file:** `tests/fakes/fake_keyword_planner.py` (pattern: `infrastructure/google_ads/fake_mutations.py`) — records calls, returns canned `KeywordIdea`s.
- **Acceptance:** fake satisfies the Protocol; used by A4 tests.

### A4 — Wire into the proposal pipeline
- **Modify:** `adcopilot/application/use_cases/launch/generate_proposal.py`
  - Constructor: accept optional `keyword_planner: KeywordPlannerPort | None = None`.
  - In `_run_pipeline` (after `build_structure`, ~line 440-449): if planner present, call `keyword_ideas(seed_keywords=<structure keywords>, seed_url=brief.landing_page_url, location=brief.location)`.
  - **Enrich + filter:** drop keywords with `avg_monthly_searches == 0`; sort remaining by searches; attach `avg_monthly_searches` + bid range to each `KeywordItem` so the LLM negative/structure stages and the UI can show real demand.
  - **Budget sanity:** compare `daily_budget_micros` vs `sum(low_top_of_page_bid_micros)` × expected clicks; surface a `compliance_warnings`-style note (reuse the warning-attach pattern at lines 82-103) when budget can't buy meaningful volume.
  - Same enrichment in `_run_hybrid_pipeline` (~line 369-371) where template keywords are mapped to `KeywordItem`.
  - Fail-open: planner returns `[]` → pipeline behaves exactly as today (no regression).
- **Modify:** `adcopilot/infrastructure/llm/campaign_generator.py` — add optional `avg_monthly_searches`/`bid_low_micros`/`bid_high_micros` to `KeywordItem`; feed real volumes into the `build_structure` prompt so the model prioritises high-demand terms instead of inventing them. **Bump the structure prompt version** (new Alembic migration — prompt change is a migration per project rules; see `0057_seed_launch_ad_copy_v2_prompt.py`).
- **Acceptance:** with the fake planner, a generated proposal's keywords are ordered by real search volume, zero-volume seeds are dropped, and a low-budget brief yields a budget warning. Pipeline still succeeds with planner=None.

### A5 — Persist volumes for reporting
- **Modify:** `adcopilot/domain/launch/entities.py` (`KeywordProposal`/`AdGroupProposal`) + the launch repo (`infrastructure/db/...`) to store `avg_monthly_searches`. Alembic migration to add columns.
- **Acceptance:** proposal round-trips volume through DB; shown in the approval preview.

**Epic A estimate:** ~4–5 days. **Unblocks the single biggest credibility gap.**

---

## EPIC B — Conversion-tracking bootstrap

Today the system only *detects* macro conversions (`check_conversion_setup.py` →
`has_macro_conversion_tracking`) and hands the user a GTM guide (`domain/conversion_tracking/installation_guides.py`).
It cannot create a conversion action or verify one fires. Uploads already exist
(`measurement_mutations_adapter.py`), so the plumbing pattern is proven.

### B1 — Extend the mutations port with conversion-action creation
- **Modify:** `adcopilot/application/ports/google_ads_mutations.py` (`GoogleAdsMutationsPort`)
  - `async def create_conversion_action(self, refresh_token, customer_id, *, name: str, category: str, value_micros: int | None, counting_type: str = "ONE_PER_CLICK", default_currency: str = "PLN") -> int` (returns conversion_action_id).
  - `async def get_conversion_action_tag_snippets(self, refresh_token, customer_id, conversion_action_id: int) -> dict` (returns the `AW-<id>/<label>` global-site-tag + event snippet — parse with existing `domain/conversion_tracking/tag_parsing.py`).
- **Acceptance:** Protocol updated; `fake_mutations.py` extended to satisfy it.

### B2 — Adapter implementation
- **Modify:** `adcopilot/infrastructure/google_ads/mutations_adapter.py`
  - Use `ConversionActionService` (`ConversionActionOperation`), `type_ = WEBPAGE`, `category` from a validated enum, `value_settings` for value-based conversions, enhanced-conversions-for-leads flag where applicable.
  - Read tag snippets via `ConversionActionService.get_conversion_action` + the `tag_snippets` field.
- **Acceptance:** integration test (skipped without creds) creates a `LEAD` action in a test account and returns a non-empty snippet.

### B3 — "Set up tracking" use case
- **New file:** `adcopilot/application/use_cases/launch/setup_conversion_tracking.py`
  - Input: account, desired macro category (PURCHASE/LEAD/SIGNUP/PHONE_CALL), optional value.
  - Reuse `has_macro_conversion_tracking` (`check_conversion_setup.py`) to no-op if one already exists.
  - Create the action (B1), fetch the snippet, then hand off to the right platform guide in `installation_guides.py` (WordPress/WooCommerce/Wix/Squarespace) pre-filled with the real `AW-…/label`.
- **Acceptance:** unit test with fakes: no existing action → creates one + returns a pre-filled Polish guide; existing action → returns "already configured".

### B4 — Verify-it-actually-fires loop
- **New file:** `adcopilot/application/use_cases/launch/verify_conversion_firing.py`
  - Poll `query_conversion_actions` (exists in `queries.py`) for `status` and recent conversion stats, OR drive a `validate_only` test upload via the existing `MeasurementUploadPort.upload_click_conversions(..., validate_only=True)` to confirm the action accepts events.
  - Surface result via the same Telegram-message return pattern `check_conversion_setup.py` uses.
- **Acceptance:** returns a clear "tracking confirmed / not yet detected — here's why" status; covered by unit tests with `FakeMeasurementUpload`.

### B5 — Gate the launch on tracking (don't just warn)
- **Modify:** `generate_proposal.py` / launch orchestration — for LEAD/PURCHASE goals, require B3 to have run (or an explicit user override) **before** `create_campaign.py` enables spend. Today the check happens *after* creation (`check_conversion_setup.py` docstring: "Called after campaign creation").
- **Acceptance:** launching a conversion-goal campaign with no tracking routes the user through B3 first; smart-bidding strategies are blocked until a macro action exists (ties into existing `bidding_resolver`).

**Epic B estimate:** ~4–6 days. **This is the agency's core value — own it.**

---

## EPIC C — Conversion-lag handling in detection rules

Week-over-week rules compare `ctx.campaigns` vs `ctx.prev_campaigns` (7-day-ago snapshot) with no grace
period for conversions still landing. For long sales cycles this fires false "CPA spike — pause!" alerts.
Affected rules: `rule_11_ctr_decline`, **`rule_12_cpa_spike`**, `rule_13_conversion_rate_drop`,
`rule_15_spend_acceleration`, `rule_36_relax_target_cpa`.

### C1 — Per-vertical attribution windows (domain)
- **New file:** `adcopilot/domain/polish_market/attribution_windows.py` (sits beside `seasonality.py`)
  - `def attribution_window_days(vertical: str | None) -> int` — e.g. e-commerce/salon/restaurant ≈ 3–7; prawnik (law)/real-estate/B2B ≈ 30–60. Default 14.
  - Pure function, fully unit-tested (mirrors `get_seasonal_multiplier`).
- **Acceptance:** table-driven unit tests for representative verticals + default.

### C2 — Carry vertical + lag into `DetectionContext`
- **Modify:** `adcopilot/application/detection/base.py` (`DetectionContext`) — add `vertical: str | None = None` and `attribution_window_days: int = 14`.
- **Modify:** `adcopilot/application/use_cases/run_detection.py` (the only place `DetectionContext(...)` is built) — populate `vertical` from the account's stored vertical and `attribution_window_days` from C1.
  - **Note / sub-task:** `GoogleAdsAccount` (`domain/entities.py`) has **no `vertical` field today** — only `CampaignBrief.vertical` exists (`domain/launch/entities.py:281`). Add `vertical` to the account (or a per-account settings row) + Alembic migration, set it at launch time. This is a prerequisite.
- **Acceptance:** context exposes vertical + window; `run_detection` tests assert they're populated.

### C3 — A reusable lag guard + apply to the 5 rules
- **New helper:** `adcopilot/application/detection/lag_guard.py`
  - `def conversions_settled(snapshot_date: date, window_days: int, today: date) -> bool` — True only if the comparison window is older than the attribution window (conversions have had time to land).
  - Optional: a "still-maturing" annotation so the UI can show "wynik wstępny — konwersje wciąż spływają" instead of a hard alert.
- **Modify rules:** in `rule_12_cpa_spike.py` (and 11/13/15/36), early-return (or downgrade severity HIGH→INFO) when `not conversions_settled(ctx.snapshot_date, ctx.attribution_window_days, today)`. Keep the existing `_MIN_CONVERSIONS` floor.
- **Acceptance:** unit test — a law-firm account (60-day window) with a fresh CPA jump produces **no HIGH alert**; a salon (7-day window) with the same data does. Existing rule tests still pass.

### C4 — (Stretch) apply seasonality to CPA/CTR rules too
- Seasonality currently only touches budget reallocation (`rule_33`). Inject `get_seasonal_multiplier` into the CPA/CTR spike thresholds so an August-expensive vertical isn't flagged as "broken".
- **Acceptance:** seasonal month widens the spike threshold; covered by tests.

**Epic C estimate:** ~2–3 days (C4 +1). **Removes the trust-killing false positives.**

---

## EPIC D — Ship the Telegram bot on main

The working interview/launch bot lives **only** in an uncommitted worktree
(`.claude/worktrees/flamboyant-kirch-0ca947/adcopilot/infrastructure/telegram/`). On `main`,
`adcopilot/interfaces/bot/` contains just an empty `__init__.py`. Per CLAUDE.md the Telegram bot is the
*primary user interface* — it cannot ship from a worktree.

### D1 — Reconcile worktree vs main
- Diff the worktree's `interview_handler.py` / handlers against `main`; identify what else the branch touched (likely launch wiring).
- Decide canonical location: project convention is `adcopilot/interfaces/bot/` (the empty dir). The worktree used `infrastructure/telegram/` — **pick one** and move accordingly (interfaces layer is correct per hexagonal: bot is a delivery mechanism).
- **Acceptance:** a single, agreed location; no duplicate bot code.

### D2 — Bring the code onto a real branch
- In `backend/` (per CLAUDE.md git rules — never from `ads-main/`): `git checkout -b feature/telegram-bot`, move files into `adcopilot/interfaces/bot/`, wire DI (planner from Epic A, tracking-setup from Epic B) in the bot's composition root.
- **Acceptance:** `from adcopilot.interfaces.bot...` imports resolve on main branch; app boots.

### D3 — Tests + CI
- Port/author handler tests (FSM transitions Q1–Q6, `/approve`, `/skip`, enable step) into `tests/`.
- **Acceptance:** bot tests run in CI; the 6-question launch flow is covered end-to-end with fakes.

### D4 — Deploy wiring
- Confirm `railway.toml` / `start.sh` / `Dockerfile` launch the bot process (or Celery worker) alongside FastAPI; `TELEGRAM_BOT_TOKEN` read from env (already in `.env.example`).
- **Acceptance:** bot responds to `/start` in a staging deploy.

**Epic D estimate:** ~2–4 days depending on worktree drift. **Without this there is no shippable product.**

---

## Suggested order
1. **D** (you have no product until the bot is on main).
2. **B** (tracking) and **C** (lag) in parallel — both are trust/correctness, low external risk.
3. **A** (keyword research) — highest value, but depends on geo mapping + a prompt-version migration; do it once the flow above is solid.

## Cross-cutting (do alongside, not blocking)
- Add retry/back-off around Google Ads calls — quota errors are *detected* (`queries.py:63`) but never retried. A small decorator in `infrastructure/google_ads/` covers A2 + B2.
- Every prompt change (A4) is an Alembic migration, not an edit (project rule).
