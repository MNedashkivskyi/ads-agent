# Orphaned endpoints — disposition (ADW-018)

The functionality audit found ~30% of the API was built but had no frontend
caller. This file records the deliberate decision for each, so no orphan is
ambiguous. Three dispositions:

- **surface** — valuable + cheap to expose; wire a UI.
- **internal** — intentionally has no UI; called by Celery / other backend
  code or feeds the rule engine. Leave as-is.
- **deferred** — built but post-MVP; kept behind a flag, not surfaced (see
  ADW-010). Do not delete.

| Router / endpoint | Disposition | Rationale |
|---|---|---|
| `dashboard.py` → `recommendations/impact` | **surface** | High-value social proof ("what your approved changes achieved"). Surfaced on the Dashboard (ADW-018 frontend). |
| `search_terms.py` (list + block) | **surface** | Done — wired to the "Wyszukiwane hasła" screen (ADW-008). |
| `billing.py` → checkout / portal | **surface** | Done — wired to the Settings billing UI (ADW-005). |
| `digest.py` → POST digest | **internal** | Triggered by the daily-digest Celery beat; no user action needed. |
| `snapshots.py` → account snapshots | **internal** | Triggered by the nightly snapshot Celery beat / account sync. |
| `landing_page.py` → score | **internal** | Feeds the landing-page audit rule; consumed by the engine, not a screen. |
| `insights.py` → weekly insights | **internal** | Delivered to the user via notifications (the bell), not a dedicated page. |
| `conversion_tracking_guide.py` → guide | **internal** | The in-app conversion-tracking flow uses the audit/setup/verify endpoints; the static guide is a backend helper. |
| `dashboard.py` → `campaigns/structure` | **deferred** | Standalone account-structure screen is deferred (ADW-010); overlaps engine rules 52–54. |
| `dashboard.py` → `benchmarks` | **deferred** | Produces nothing until ≥5 accounts exist; do not surface an empty screen. Code/schedule kept. |
| `pmax.py` (entire router) | **deferred** | PMax *creation* targets a narrow e-commerce/Growth slice; deferred (ADW-010). Shopping *health* stays. |
| `qa.py` (ask + history) | **deferred** | Client Q&A assistant is post-MVP; backend kept, no UI yet. |
| `users.py` → `start-trial`, `approve-bulk` | **internal** | `start-trial` is provisioning logic; bulk-approve is available for future UI but single approve/decline covers MVP. |

## Rule going forward
Every new endpoint must be one of: surfaced in the UI, called by another
backend component (internal), or explicitly flagged deferred. No endpoint
should ship with no caller and no entry here.
