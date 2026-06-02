from __future__ import annotations

from adcopilot.domain.recommendation import Confidence, confidence_from_volume


def test_high_confidence_from_conversions() -> None:
    assert confidence_from_volume(conversions=5) is Confidence.HIGH
    assert confidence_from_volume(clicks=120) is Confidence.HIGH
    assert confidence_from_volume(impressions=6000) is Confidence.HIGH


def test_medium_confidence() -> None:
    assert confidence_from_volume(conversions=1) is Confidence.MEDIUM
    assert confidence_from_volume(clicks=20) is Confidence.MEDIUM
    assert confidence_from_volume(impressions=500) is Confidence.MEDIUM


def test_low_confidence_thin_data() -> None:
    assert confidence_from_volume(impressions=100, clicks=2) is Confidence.LOW
    assert confidence_from_volume() is Confidence.LOW


def test_recommendation_defaults_to_medium_confidence() -> None:
    # Backward compatibility: existing constructors get MEDIUM without changes.
    import uuid
    from datetime import UTC, datetime

    from adcopilot.domain.recommendation import (
        Recommendation,
        RecommendationKind,
        RecommendationSeverity,
        RecommendationStatus,
    )

    rec = Recommendation(
        id="r1",
        account_id="a1",
        kind=RecommendationKind.PAUSE_KEYWORD,
        severity=RecommendationSeverity.MEDIUM,
        target={"campaign_id": 1},
        payload={},
        estimated_monthly_savings_micros=0,
        evidence={},
        created_at=datetime.now(UTC),
        status=RecommendationStatus.PENDING,
    )
    assert rec.confidence is Confidence.MEDIUM
    _ = uuid  # silence unused
