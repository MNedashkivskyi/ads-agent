# Phase 5 (Agency go-to-market) — FROZEN

**Status: paused / hidden behind a feature flag (as of 2026-06-19).**

Phase 5 was built but is intentionally **switched off** for now. Nothing in Phase 5
is visible or callable in the product until the flag is flipped. The code remains in
the repo, tested, ready to re-enable — this is a freeze, not a revert.

## The flag

| Side | Flag | Default | Effect when OFF |
|------|------|---------|-----------------|
| Backend | `PHASE_5_ENABLED` (env / Settings) | `False` | Phase 5 endpoints respond **404** |
| Frontend | `VITE_PHASE_5_ENABLED` (build env) | `false` | Phase 5 nav links + routes hidden (routes redirect to `/app`) |

**To unlock Phase 5:** set `PHASE_5_ENABLED=true` on the backend (Railway → `adswise-backend`)
**and** `VITE_PHASE_5_ENABLED=true` on the frontend (Railway → `adswise-frontend`), then
redeploy both. Both must be on.

## What gets hidden when frozen

**Backend endpoints (404 when `PHASE_5_ENABLED` is false)** — gated via
`adcopilot/interfaces/api/deps.py::require_phase5_enabled`:
- `GET /api/audit/portfolio` — recovery portfolio rollup
- `GET /api/audit/agency/prospects`, `POST /api/audit/agency/prospects/{id}/status` — agency prospects
- `GET/POST/DELETE /api/{user_id}/organization/...`, `POST /api/organizations/invitations/{token}/accept` — team seats
- `POST /api/{user_id}/reports/cross-account` — cross-account report

**Frontend (hidden when `VITE_PHASE_5_ENABLED` is false)** — via `src/lib/flags.ts`:
- `/app/portfolio`, `/app/team`, `/app/invite/$token`, `/app/cross-account-report` (nav links + routes)

## What was built in Phase 5 (all merged, all tested)

- **5A — surface the built foundation** (ads-agent #299; approve-ads-bot #148/#149/#150):
  portfolio rollup, team-seat management UI + invites, cross-account branded report UI.
- **5B — org-owned accounts** (ads-agent #300/#301/#302): accounts belong to an
  organization; access is "owner **or** org member" (`can_access_account`); listing is
  org-aware; per-plan account quota counts *owned* accounts.
- **5C — agency prospecting (foundation only)** (ads-agent #303/#304): prospect model +
  status + list/status API, and encrypted MCC-link storage. The **live** pieces (MCC
  OAuth connect, child-account listing, scan-via-`login_customer_id`, prospects
  dashboard) were never built — they need staging/MCC access.

## What is NOT affected by the freeze (stays on)

- The core **audit → recovery loop** (free audit, reveal, onboarding bridge, recovery
  meter, findings→fixes) — Phases 0–4, unrelated to the Phase 5 flag.
- **5B's account-access plumbing** stays in place. It's inert for solo users (you see
  only your own accounts, exactly as before); org sharing only matters once a team
  exists, and team creation is itself frozen. Reverting it was unnecessary and riskier.
- The **campaign/account authorization hardening** (ads-agent #305) — a security fix,
  kept on.

## Re-enabling later

1. Build the remaining 5C live pieces with staging/MCC access (see project memory).
2. Optionally build **5D** (persistent white-label branding).
3. Flip `PHASE_5_ENABLED` + `VITE_PHASE_5_ENABLED` to true and redeploy.
4. Walk the staging runbook (`docs/audit_loop_verification.md`) plus: invite a teammate,
   confirm shared-account access, generate a cross-account report.
