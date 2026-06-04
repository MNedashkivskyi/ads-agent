# Causal Measurement — Native Google Ads Experiments

## Why

The product previously proved value with **before/after** comparisons
(`compare_recommendation_performance`). That is **observational**: auctions,
seasonality and Smart-Bidding learning move metrics on their own, so "we changed X
and CPA dropped" does not prove X caused the drop. Sophisticated clients see through
correlational claims.

This feature adds **true causal measurement**: an impactful change (first: bidding
strategy / target CPA / target ROAS) is run as a **native Google Ads campaign
experiment** — a `CampaignDraft` + `Experiment` with a Google-managed traffic split —
so the change's lift is measured against a real control arm with statistical
significance, and promoted only if it wins. It also **stops presenting before/after as
proof** by grading every performance claim's evidence strength.

## Lifecycle

```
PROPOSED ──launch──▶ RUNNING ──evaluate──▶ EVALUATED ──promote──▶ PROMOTED
                        │                       │
                        └──────── end ──────────┴────────────────▶ ENDED
(any Google Ads failure ▶ FAILED, surfaced to the user)
```

- **Propose** (`POST /api/{user}/causal-experiments/propose`): creates a draft of the
  base campaign, applies the bidding change *to the draft*, then creates + schedules a
  50/50 experiment. Human-approved — never auto-launched.
- **Evaluate** (daily `evaluate_campaign_experiments_task`, 06:30 UTC): reads per-arm
  metrics, runs the two-proportion z-test (reused from `evaluate_experiment`), sets a
  verdict (`WIN`/`LOSS`/`INCONCLUSIVE`) once significant or the window closes, and
  notifies the user. **No auto-promotion.**
- **Promote / End** (`.../promote`, `.../end`): explicit, human-approved. A `WIN` can be
  graduated to the base campaign; anything else can be ended.

## Honesty layer (`domain/evidence_grading.py`)

Every performance claim is graded:

- `OBSERVATIONAL` — before/after delta, not statistically distinguishable.
- `OBSERVATIONAL_SIGNIFICANT` — significant delta, **still confounded** (not causal).
- `CAUSAL` — backed by a native experiment with a control arm.

The dashboard "before/after" cards now carry `evidence_grade` + a Polish caveat, and
upgrade to `CAUSAL` when a `CampaignExperiment` validated that recommendation. The
weekly report's period-over-period comparison is labelled observational.

## Components

| Layer | File |
|---|---|
| Domain | `domain/campaign_experiment.py`, `domain/evidence_grading.py` |
| Port | `application/ports/experiment_mutations.py` |
| Adapter | `infrastructure/google_ads/experiment_mutations_adapter.py` |
| Use cases | `application/use_cases/campaign_experiment_flow.py` |
| Storage | `campaign_experiments` table (migration `0063`), `repositories/campaign_experiment_repository.py` |
| Task | `evaluate_campaign_experiments_task` (daily beat) |
| API | `interfaces/api/causal_experiments.py` (`/api/{user}/causal-experiments…`) |
| Frontend | `routes/app/causal-experiments.tsx`, `e2e/causal-experiments.spec.ts` |

## Testing & live validation

- **Unit-tested:** domain transitions, the pure metrics parser (`_parse_metrics`), the
  verdict decision (`decide_verdict`), the full launch/evaluate/promote flow with a
  fake adapter, the API response mapping, and evidence grading.
- **Live-validated (no `validate_only` exists for drafts/experiments):** the proto
  construction in `experiment_mutations_adapter.py` (`CampaignDraftService`,
  `ExperimentService`, `ExperimentArmService`) is only fully confirmable by launching a
  real experiment on a live account. The machinery + honesty reframe ship now; causal
  verdicts mature over the experiment window (default 14 days). `get_experiment_metrics`
  is wired live (its tested core is `_parse_metrics`).

## Guardrails

- Human-in-the-loop: experiments are proposed/launched and promoted only on explicit
  user action — never automatically.
- Failures mark the experiment `FAILED` with the error surfaced; no silent failures.
- All user-facing copy is Polish.
