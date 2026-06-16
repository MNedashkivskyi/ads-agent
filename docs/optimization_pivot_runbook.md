# Optimization pivot — deployment runbook (T6.5)

Two independent repositories deploy separately on Railway: `adswise-backend`
(this repo) and `adswise-frontend`. **Deploy backend first, then frontend.** The
backend is the real gate; frontend gating is defense-in-depth and must never
ship ahead of the backend (R8).

## Pre-flight

- Confirm the new env flags are set at the Railway project level (both default
  safe, so absence = off):
  - `CAMPAIGN_CREATION_ENABLED` — keep **False** (greenfield creation stays off).
  - `AUTO_APPLY_GLOBALLY_ENABLED` — keep **False** until you explicitly enable
    auto-apply platform-wide.
- Confirm the three recurring Stripe price IDs are set
  (`STRIPE_STARTER_PRICE_ID`, `STRIPE_PRO_PRICE_ID`, `STRIPE_BUSINESS_PRICE_ID`).
  `STRIPE_SETUP_FEE_PRICE_ID` is no longer referenced and can be removed.
- CI is green, including the **Entitlement matrix gate** step.

## Step 1 — Backend

1. Merge the backend pivot branches to `master` in phase order (0 → 6). Each
   phase was shipped as its own PR.
2. Run Alembic migrations (Railway release command or `make migrate`):
   - `0075` deprecate launch prompts (data-preserving flag).
   - `0076` auto_apply_settings.
   - `0077` api_keys.
   - `0078` organizations / memberships / invitations + idempotent personal-org
     backfill.
   All are reversible; `0078`'s backfill is idempotent (safe to re-run).
3. The Professional account-limit change (1 → 3) is **config-only** — it takes
   effect immediately on deploy, no migration or data change. Existing
   Professional users can link a 3rd account right away.
4. Verify boot: `/health` is green; the worker boots and registers CIE +
   optimization tasks; creation tasks are inert no-ops while the kill-switch is
   off.

## Step 2 — Frontend

1. Merge the frontend pivot branches to `main`.
2. Deploy. The new tier copy, gating parity, 14-day trial, and spend-band
   messaging go live. `VITE_ENABLE_DEFERRED` no longer reveals the (removed)
   creation wizard.

## Smoke tests (post-deploy)

Backend (per tier — use a test account on each plan):
- STARTER: gated routes (`/audiences`, `/experiments`, `/measurement`, PMax,
  insights `/ask`) return **403** with a Polish upgrade message; Core routes
  (recommendations, conversion-tracking, quality-score, spend-safety, dashboard,
  search-term waste) return **200**.
- PROFESSIONAL: the above gated routes pass; Business-only routes
  (causal-experiments, cross-account reports, org, api-keys) return **403**.
- BUSINESS: all of the above pass; can link a 4th+ account; can create an API
  key and call `/api/public/recommendations` with `X-API-Key`.
- Greenfield: `/api/launch/...` and PMax create/eligibility return **404**
  (kill-switch off).
- Billing: subscribe → plan unlocks; cancel → downgrades to STARTER; trial is
  14 days.

Frontend:
- Per-tier nav walkthrough matches the ladder; gated pages show the upgrade
  notice for unentitled tiers; Core pages visible to all; admin sees everything.
- Pricing shows 1 / 3 / unlimited accounts, spend ceilings, 14-day trial, and
  zero campaign-creation / setup-fee copy.

## Rollback

- **Frontend:** redeploy the previous build (no schema coupling).
- **Backend code:** redeploy the previous image.
- **Migrations:** each pivot migration has a `downgrade()`; run
  `alembic downgrade -1` per step if a schema rollback is required. The new
  tables are additive, so a code rollback alone is usually sufficient (the old
  code simply ignores them).
- **Feature flags:** flipping `CAMPAIGN_CREATION_ENABLED=True` instantly
  restores greenfield creation routes without a deploy (the reversible
  kill-switch). `AUTO_APPLY_GLOBALLY_ENABLED=False` halts all automated
  execution instantly.

## After a stabilization window (~30 days)

Run T6.2 (physical deletion of the hidden creation code) once the kill-switch
has been stable in production. See `docs/phase1_launch_domain_audit.md` for the
move-before-delete list.
