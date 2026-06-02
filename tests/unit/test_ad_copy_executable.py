"""Phase 1: the ad-copy cluster (single ad, ad↔keyword mismatch, missing CTA,
redundant headlines, generic description) is now auto-executable via the shared
AdCopyRefreshExecutor (creates a fresh RSA in the ad group).
"""

from __future__ import annotations

import pytest

from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS, RecommendationKind

AD_COPY_KINDS = [
    RecommendationKind.ADD_AD_VARIATION,
    RecommendationKind.AD_KEYWORD_MISMATCH,
    RecommendationKind.MISSING_CTA,
    RecommendationKind.REDUNDANT_HEADLINES,
    RecommendationKind.GENERIC_DESCRIPTION,
]


@pytest.mark.parametrize("kind", AD_COPY_KINDS)
def test_ad_copy_kinds_are_executable(kind: RecommendationKind) -> None:
    # Drives is_executable in the API and the approve-endpoint guard.
    assert kind not in NON_EXECUTABLE_KINDS


@pytest.mark.parametrize("kind", AD_COPY_KINDS)
def test_ad_copy_kinds_have_a_wired_executor(kind: RecommendationKind) -> None:
    from adcopilot.application.use_cases.execute_recommendation import _default_executors

    registry = _default_executors()
    assert kind in registry
