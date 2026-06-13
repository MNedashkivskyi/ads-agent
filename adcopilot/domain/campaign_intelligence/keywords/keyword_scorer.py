"""keyword_scorer — pure ranking logic for keyword candidates.

``score = log10(volume) × intent_weight × competition_weight``

``intent_weight`` is *injected*: static priors now (PROBLEM/INTENT > BRAND), the
learned per-vertical weight later (Phase 6). The log of volume keeps a
1,000,000-search head term from drowning out a solid 5,000-search intent term by
sheer scale while still rewarding real demand. Non-viable or zero-volume
candidates score exactly 0 and are rejected. Pure and deterministic.
"""

from __future__ import annotations

import math

from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
)
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KeywordIntent,
    KeywordScore,
    SearchVolume,
)


def compute_score(volume: SearchVolume, intent_weight: float) -> KeywordScore:
    """Score a single (volume, intent_weight) pair. Non-viable → 0."""
    if volume is None or not volume.is_viable or volume.monthly_searches <= 0:
        return KeywordScore.zero()
    base = math.log10(max(volume.monthly_searches, 1))
    return KeywordScore(base * intent_weight * volume.competition_weight)


def intent_weight_for(
    intent: KeywordIntent, learned_weights: dict[str, float] | None = None
) -> float:
    """Resolve the intent-weight: learned value if present, else static prior."""
    if learned_weights and intent.value in learned_weights:
        return learned_weights[intent.value]
    return intent.default_weight


def score_candidate(
    candidate: KeywordCandidate,
    learned_weights: dict[str, float] | None = None,
) -> KeywordScore:
    """Compute and attach a score to *candidate* in place; return the score.

    A candidate with no/zero/non-viable volume scores 0 and is marked rejected.
    """
    if candidate.volume is None:
        score = KeywordScore.zero()
    else:
        weight = intent_weight_for(candidate.intent, learned_weights)
        score = compute_score(candidate.volume, weight)
    candidate.with_score(score)
    if score.value <= 0.0:
        candidate.mark_rejected()
    return score
