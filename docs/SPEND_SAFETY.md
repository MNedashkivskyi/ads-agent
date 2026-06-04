# Spend-Safety System

## Why
An autonomous agent that can raise budgets, change bidding strategies and relax
target-CPA must not be able to blow a client's budget — and must catch a real-world
spend runaway fast. Budget tier was advisory only, the agent's own spend actions were
ungated, and anomaly detection alerted but never protected. This system closes that
gap with two halves:

1. **Preventive guardrail** — validates the agent's *own* spend-increasing mutations
   against per-account caps **before** they execute (makes CLAUDE.md's "budget tier
   integrity, no bypass" real).
2. **Reactive circuit-breaker** — monitors realized spend hourly and escalates a
   breach: always notify; **auto-pause only when the account opts in**.

## Configuration (`SpendSafetyConfig`, opt-in)
Per-account caps (all `None` = no limit; the system is inert until at least one is set):
- `monthly_spend_cap_micros` — account total/month (pace-aware projection).
- `daily_spend_cap_micros` — account total/day.
- `per_campaign_daily_cap_micros` — each campaign/day; the offending campaign is paused.
- `max_budget_increase_pct` (default 50) — cap on a single budget-raise (and tCPA-relax) action.
- `warning_threshold_pct` (default 80) — % of a cap at which to warn.
- `auto_pause_enabled` (default **false**) — gates automatic pausing.

Stored in `spend_safety_config` (migration **0064**); API `GET/PUT /api/{user}/spend-safety`
and `GET /api/{user}/spend-safety/status`; frontend `routes/app/spend-safety.tsx`.

## Half 1 — Preventive guardrail (`domain/spend_guard.py`)
Pure `evaluate_spend_action(action, config, ctx)` → allow/deny. Covers single-campaign
spend *raises* with a numeric delta — budget increases and tCPA relaxation. Denies when:
- a single budget raise (or tCPA relaxation) exceeds `max_budget_increase_pct`,
- the new campaign budget exceeds the per-campaign daily cap,
- today's account spend + the raise exceeds the daily cap,
- the pace-aware month-end projection + the raise exceeds the monthly cap.

Wired in `use_cases/execute_recommendation.py` between the `campaign_exists` pre-flight
and the executor. A denial raises `SpendGuardViolation` (terminal, no retry); the worker
marks the rec FAILED and sends a Polish notification (no silent failure). Reallocation
(net-zero at account level) and bidding-strategy switches (no numeric delta) are out of
the guard's scope — the reactive breaker covers their realized spend.

## Half 2 — Reactive circuit-breaker (`domain/spend_breach.py`)
Pure `detect_spend_cap_breaches(...)` grades caps WARNING (≥ threshold) / BREACH (≥ cap,
pace-aware for monthly). `decide_escalation(breach, config)`:
- always notify (Polish alert, `AlertKind.SPEND_CAP_BREACH`),
- BREACH + `auto_pause_enabled`: campaign scope → `pause_campaign`; account scope → `panic_pause_campaigns_task`,
- BREACH without opt-in: human-approved pause proposal,
- WARNING: notify only.

Driven hourly by `detect_spend_cap_breaches_task` (beat `:20`), per-account isolated,
with an `AuditLog` row for every auto-pause.

## Protective action (`SS2`)
`GoogleAdsMutationsPort.pause_campaign` + adapter (CampaignService update → status PAUSED;
proto live-validated) + `RecommendationKind.PAUSE_CAMPAIGN` + `PauseCampaignExecutor`.

## Detection context
`SpendSafetyConfig` is threaded into `DetectionContext` (alongside `business_economics`)
so future rules can anchor budget/pacing suggestions to the user's caps.

## Testing & live validation
- **Unit-tested:** config validation, guard allow/deny matrix (incl. pace projection),
  execution-path block, breach detection per cap type, escalation routing, pause executor +
  adapter boundary, detection-context wiring, API response mapping.
- **Live-validated (post-deploy, dev account):** the `pause_campaign` proto (no `validate_only`),
  and end-to-end: set a low cap → a violating budget-raise is blocked with a Polish reason →
  a simulated breach notifies → with auto-pause on, the campaign/account is paused + audited.

## Guardrails
- Human-in-the-loop by default; auto-pause is strictly opt-in per account.
- Opt-in caps: no behaviour change until the user sets a cap.
- No silent failures; all user-facing copy Polish; no new PII; every protective action audited.
