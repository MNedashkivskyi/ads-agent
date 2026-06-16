# Pivot analytics & funnel guardrails (T6.4)

The optimization pivot is instrumented with structured analytics events so we
can see whether it converts. Events are emitted via
`adcopilot.observability.analytics` as structured `structlog` records under the
`analytics` logger with a stable `event` field, and flow to the existing log
sink. The dashboard and alerts are built on these events — no third-party SDK,
and only ids / plan slugs are emitted (no PII beyond the user id we already
hold).

## Event taxonomy — the funnel: free audit → trial → paid

| Event | Emitted from | Key fields |
|---|---|---|
| `account_connected` | OAuth account-link success | `user_id`, `account_id` |
| `trial_started` | `users.get_user_me` (trial auto-start) | `user_id` |
| `subscription_changed` | `billing._handle_subscription_event` | `user_id`, `old_plan`, `new_plan`, `status`, `paid_conversion` |
| `upgrade_prompted` | `deps.require_capability` 403 | `user_id`, `plan`, `capability` |
| `feature_used` | gated feature exercised | `user_id`, `plan`, `capability` |

`paid_conversion` is `true` when a user moves from no-plan/starter to a paid
tier — the headline conversion metric.

## Dashboard (log-based)

Build these panels from the `analytics` event stream:

1. **Acquisition → activation:** count of `account_connected` and the share that
   reach `trial_started`.
2. **Trial → paid funnel:** `trial_started` → `subscription_changed` with
   `paid_conversion=true`, by week.
3. **Upgrade pressure:** `upgrade_prompted` counts grouped by `capability` and
   `plan` — which gates drive the most upsell intent.
4. **Per-tier feature usage:** `feature_used` grouped by `plan` and `capability`.
5. **Churn:** `subscription_changed` with `status in (canceled, unpaid)`.

## Alerts (guardrails)

- **Conversion drop:** alert if the 7-day trailing trial→paid rate falls below a
  threshold after a deploy (catches a pivot that stops converting).
- **Activation drop:** alert if `account_connected`→`trial_started` collapses.
- **Gate noise:** alert if `upgrade_prompted` for a single capability spikes far
  above baseline (a gate may be mis-placed or a Core feature accidentally gated).
