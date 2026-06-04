# Tier-1 Staging Smoke Test

The Tier-1 work is unit- and endpoint-tested in CI. Three things can only be
proven against a **live Postgres + a real Google Ads test account**, because the
ORM uses Postgres-only types (UUID/JSONB) and the adapters call the real Google
Ads API. Run this checklist once on staging before calling Tier-1 done.

## 0. Prerequisites
- Staging backend deployed from `feat/tier1-agency-gaps` (or after merge).
- A Google Ads **test/sandbox** account connected (OAuth completed) for a test user.
- `DATABASE_URL`, `GOOGLE_ADS_*`, `ANTHROPIC_API_KEY`, `TOKEN_ENCRYPTION_KEY` set.

## 1. Apply migrations (required, not runnable in CI sandbox)
```bash
cd backend
alembic upgrade head      # must reach 0067
alembic current           # expect: 0067 (head)
```
Verify:
- `\d launch_keywords` shows the new `avg_monthly_searches` integer column.
- `SELECT prompt_key, version FROM prompt_versions WHERE prompt_key='launch_structure';`
  returns `launch_structure | 1`.

## 2. EPIC A — keyword research (real Keyword Planner)
1. Run the launch wizard for the test account → generate a proposal (non-template path).
2. `GET /app/launch/preview/{proposal_id}` →
   - at least some keywords have a non-null `avg_monthly_searches`;
   - zero-volume seed keywords were dropped; keywords are demand-ordered.
3. Frontend: open the preview page → keyword chips show the `N/mies.` volume badge.
4. Negative control: temporarily revoke the account's refresh token → regenerate →
   proposal still succeeds (fail-open), keywords just have null volumes.

Logs to confirm: `keywords_enriched_with_demand` (success) or
`keyword_enrichment_failed` / `planner creds unavailable` (fail-open).

## 3. EPIC B — conversion-tracking bootstrap (real Google Ads writes)
> Use the **test** account — this creates a real conversion action.
1. `POST /api/conversion-tracking/setup` `{ "category": "LEAD", "platform": "wordpress" }`
   - 200, `already_configured=false`, `tag.conversion_id` like `AW-...`, `tag.event_snippet` present.
   - In Google Ads UI: a new `LEAD` conversion action named "Kontakt / Zapytanie" exists.
2. Call setup again → `already_configured=true`, nothing created.
3. `POST /api/conversion-tracking/verify` `{ "conversion_action_id": <id> }`
   - before any conversion: `found=true, enabled=true, is_firing=false`.
   - after firing a test conversion + waiting: `is_firing=true`.

## 4. EPIC B5 — enable gate (real, blocks spend)
1. Create a campaign for a **conversion goal** (e.g. `lead`) on an account with **no**
   macro conversion action → `POST /api/launch/{brief_id}/enable` →
   **409** `{error: "no_conversion_tracking", message_pl: ...}`; campaign stays PAUSED.
2. Re-send with `{ "override_conversion_check": true }` → **202** `enabling`;
   campaign goes ENABLED in Google Ads.
3. With tracking present (from step 3) → enable without override → **202**, ENABLED.
4. Frontend: the 409 surfaces the Polish `message_pl` and offers "set up tracking" / "override".

## 5. EPIC C — conversion-lag (already active in backend)
1. Ensure the test account has a classified `vertical` (column populated by
   `classify_account_vertical`). For a long-cycle vertical (`prawnik`,
   `nieruchomosci`), a week-over-week CPA spike should be created at **LOW**
   severity with `evidence.conversions_maturing = true`.
2. For a short-cycle vertical (`salon`), the same spike stays **HIGH**.

## Done criteria
- [ ] `alembic current` = 0067; both new schema changes present.
- [ ] A: real volumes shown in preview + UI badge; fail-open verified.
- [ ] B: conversion action created, no-op on repeat, verify transitions to firing.
- [ ] B5: 409 block, override enables, tracking-present enables.
- [ ] C: long-cycle downgrade vs short-cycle HIGH confirmed on real data.
