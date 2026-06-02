from __future__ import annotations

from adcopilot.domain.conversion_tracking.consent_mode import consent_mode_v2_snippet
from adcopilot.infrastructure.consent_checker import detect_measurement_signals


def test_snippet_declares_v2_signals() -> None:
    snippet = consent_mode_v2_snippet()
    assert "ad_user_data" in snippet
    assert "ad_personalization" in snippet
    assert "consent" in snippet


def test_generated_snippet_passes_the_detector() -> None:
    # Round-trip: the snippet we hand out must itself be recognized as v2.
    signals = detect_measurement_signals(consent_mode_v2_snippet())
    assert signals.consent_mode_v2 is True
    assert signals.ad_user_data is True
    assert signals.ad_personalization is True
