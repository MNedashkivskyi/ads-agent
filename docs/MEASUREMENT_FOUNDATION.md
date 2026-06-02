# Measurement Foundation (Phases 0–6)

## Why
A senior PPC review flagged **measurement** as the product's #1 gap: Smart Bidding
(tCPA/tROAS/Max Conversions) is only as good as the conversion signal it's fed, and
the product previously had only a read-only conversion-tracking audit — no
closed-loop, value-aware, consent-compliant measurement. This change builds that
foundation end-to-end for a mixed lead-gen + e-commerce book, delivered test-first
and verified live.

## What shipped

**Phase 0 — Measurement Health diagnostic** (`/app/measurement`)
A read-only diagnostic scoring six sub-scores — `conversion_actions`,
`value_tracking`, `enhanced_conversions`, `consent_mode_v2`, `ga4_link`,
`oci_readiness` — plus a live conversion-actions table. Each sub-score is driven by
a real signal, not a placeholder.

**Phase 1 — Shared ingestion core + identity store**
- `infrastructure/hashing.py`: single source of truth for normalize + SHA-256 of
  email (trim/lowercase) and phone (E.164); the existing Customer Match path now
  routes through it.
- `ConversionOutcome` domain (click ids gclid/gbraid/wbraid + hashed email/phone,
  value/currency, `NEW→QUALIFIED→WON→LOST` lifecycle, upload state, `occurred_at`).
- `conversion_outcomes` + `conversion_uploads` (audit) tables + repositories.
- Upload port + adapter over `ConversionUploadService` with **`validate_only`
  (dry-run)** and **`partial_failure`** parsing.

**Phase 2 — Offline Conversion Import (lead-gen)**
Lead intake (PII hashed server-side, raw discarded), `win`/`lose`, dedup on
`external_id`, batched upload with **dry-run-first** UI; idempotent via `order_id`;
per-batch audit; 6-hourly Celery flush task.

**Phase 2b — Conversion adjustments**
`restate(value)` / `retract()` for already-uploaded conversions (keyed by
`order_id`); `win` on an uploaded WON → restatement, `lose` on an uploaded →
retraction; flushed by the same task.

**Phase 3 — Enhanced Conversions for Leads**
Hashed-only (no-gclid) outcomes upload via `user_identifiers`; the
`enhanced_conversions` sub-score reflects the real account setting
(`customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled`).

**Phase 4 — Consent Mode v2 + Enhanced-web verification**
HTML signal detector (`ad_user_data`, `ad_personalization`, `analytics_storage`,
enhanced-web) with a best-effort site fetcher; the `consent_mode_v2` sub-score is
verified against the live landing page; `GET /consent-snippet` returns a ready
gtag v2 default block (round-trip tested: the snippet itself passes the detector).

**Phase 5 — Value-based conversions + business context**
`business_economics` (AOV, margin, LTV, target ROAS, default lead value) + editor
UI; pure value derivation (purchases → AOV×margin; leads → default/LTV); `win`
value is optional and derived when omitted; `value_tracking` → healthy once
configured.

**Phase 6 — GA4 deep integration**
GA4 conversion-totals fetch + pure GA4↔Google-Ads reconciliation
(`ALIGNED`/`GA4_HIGHER`/`ADS_HIGHER`/`NO_DATA`, signed discrepancy %) surfaced as a
card.

## API surface (all under `/api/{user_id}/measurement`)
`GET /health` · `GET /consent-snippet` · `GET|PUT /business-context` ·
`GET /reconciliation` · `POST|GET /leads` · `POST /leads/{id}/win` ·
`POST /leads/{id}/lose` · `POST /leads/upload`

## Database migrations
- `0058` conversion_outcomes + conversion_uploads
- `0059` adjustment columns (pending_adjustment, adjusted_at)
- `0060` business_economics

## Safety & compliance
PII stored **hashed-only** (raw discarded; nothing sensitive in logs/URLs) ·
uploads **default to dry-run**, real upload is an explicit action · idempotent
retries (`order_id`) · every batch audited · upload task rate-limited/batched ·
all external fetches best-effort (never hard-fail the diagnostic) · Polish
user-facing copy · theme-token UI (dark-mode safe).

## Testing
- ~40 new backend unit tests; full suite **1562 passing, 1 skipped**.
- Pure logic (hashing, value derivation, reconciliation, scoring, upload
  interpretation) unit-tested; repos verified against real Postgres in rolled-back
  transactions; adapters tested at the boundary with mocked Google responses.
- New Playwright E2E specs (`measurement.spec.ts`, `measurement-leads.spec.ts`).

## Live verification (dev)
Walked the full flow on the deployed dev env against the real Google Ads account:
diagnostic (real data), economics save → `value_tracking` healthy, lead intake →
win → retract, value auto-derivation, consent snippet, reconciliation. The dry-run
upload with a real conversion-action id **reached Google's `validate_only` API**
and returned a genuine partial-failure (fake gclid rejected) — proving the proto
build + validation + error parsing end-to-end. No bugs found.

## Known limitations / follow-ups
- A *successful* real conversion upload needs a genuine GCLID; GA4 reconciliation
  needs GA4 linked — both code paths proven at the boundary, will light up with
  real data.
- Telegram parity for lead actions not built (web + API cover it).
- Consent/enhanced-web detection is heuristic (HTML scan), not a headless render.
