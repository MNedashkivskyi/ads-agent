# Business-Context Onboarding + Economics Anchoring

## Why
The engine optimized platform metrics (CTR/QS/CPA-vs-history) but didn't know the
client's business — goal, margins, acceptable CPA/ROAS, capacity, brand/exclusions
— so recommendations floated free of economics. This work captures that context and
anchors recommendations to it.

## What shipped

**Capture (BC1)** — extends the Phase-5 `business_economics` (migration `0062`):
- `primary_goal` (LEADS | SALES | AWARENESS | CALLS)
- `target_cpa` (currency units) + existing `target_roas`
- `monthly_conversion_capacity`
- `brand_terms`, `excluded_terms` (JSONB lists)
- `BusinessEconomics.is_context_configured()`; `GET/PUT /api/{user}/measurement/business-context`
  carry the new fields. Backward-compatible (nullable).

**Onboarding wizard (BC2)** — `/app/onboarding`, 4 steps (goal → economics →
targets+capacity → brand/exclusions) saving via PUT. Nav link "Kontekst biznesowy";
theme-token UI.

**Anchor explanations (BC3)** — `ExplainRecommendationUseCase` injects a compact
economics line (goal, target CPA/ROAS, margin, capacity) into the explanation
prompt, so **every** recommendation is framed against the client's targets.
`_generate_explanations` loads the context once per account. No-context → unchanged.

**Anchor waste rules (BC4)** — `rule_02_zero_conversion_keyword` and
`rule_01_wasted_search_term` judge waste against the client's **target CPA** when
configured (full CPA / 30%-of-CPA floor) instead of a multiple of historical
average; evidence records `threshold_basis`. Falls back to the prior avg-based
behavior when no target.

## Tests
~10 new unit tests (context model, explanation anchoring with a fake LLM, waste
rules target-vs-no-target) + repo verified against real Postgres in a rolled-back
transaction. Full backend suite green (1608).

## Scope / follow-ups
- "Anchor every recommendation" = explanation-layer framing (all recs) + target-CPA
  detection on the two highest-impact waste rules. Reworking all 59 rule thresholds
  is a deliberate follow-up (e.g. cpa_spike).
- brand/excluded terms are **captured** but not yet **acted on** (brand-protection
  negatives / auto-exclusions = future rule + executor).
- Migration `0062` must run on deploy.
