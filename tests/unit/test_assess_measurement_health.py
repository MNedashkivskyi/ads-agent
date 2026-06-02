from __future__ import annotations

from dataclasses import dataclass

from adcopilot.application.use_cases.assess_measurement_health import assess_measurement_health
from adcopilot.domain.measurement import SUBSCORE_KEYS, MeasurementStatus


@dataclass
class FakeAction:
    name: str
    category: str
    status: str
    all_conversions: float


def _by_key(report, key):
    return next(s for s in report.subscores if s.key == key)


def test_no_conversion_actions_is_missing() -> None:
    report = assess_measurement_health([], ga4_linked=False)

    assert report.overall_status is MeasurementStatus.MISSING
    # All six sub-scores are always present and keyed consistently.
    assert [s.key for s in report.subscores] == list(SUBSCORE_KEYS)
    assert _by_key(report, "conversion_actions").status is MeasurementStatus.MISSING
    assert _by_key(report, "ga4_link").status is MeasurementStatus.MISSING
    assert report.conversion_actions == []


def test_lead_gen_receiving_conversions_needs_attention() -> None:
    actions = [
        FakeAction("Formularz", "SUBMIT_LEAD_FORM", "ENABLED", 42.0),
        FakeAction("Telefon", "PHONE_CALL_LEAD", "ENABLED", 0.0),
    ]

    report = assess_measurement_health(actions, ga4_linked=False)

    # Overall can't be HEALTHY in Phase 0 (enhanced/consent are placeholders).
    assert report.overall_status is MeasurementStatus.NEEDS_ATTENTION
    assert _by_key(report, "conversion_actions").status is MeasurementStatus.HEALTHY
    # Lead categories present -> offline import is a real opportunity.
    assert _by_key(report, "oci_readiness").status is MeasurementStatus.NEEDS_ATTENTION
    # Per-action health is classified.
    healths = {a.name: a.health for a in report.conversion_actions}
    assert healths == {"Formularz": "HEALTHY", "Telefon": "STALE"}


def test_ga4_link_flips_healthy_when_linked() -> None:
    actions = [FakeAction("Zakup", "PURCHASE", "ENABLED", 10.0)]

    unlinked = assess_measurement_health(actions, ga4_linked=False)
    linked = assess_measurement_health(actions, ga4_linked=True)

    assert _by_key(unlinked, "ga4_link").status is MeasurementStatus.MISSING
    assert _by_key(linked, "ga4_link").status is MeasurementStatus.HEALTHY
    # An e-commerce (value) category surfaces value tracking for confirmation.
    assert _by_key(linked, "value_tracking").status is MeasurementStatus.NEEDS_ATTENTION


def test_enhanced_conversions_healthy_when_enabled() -> None:
    actions = [FakeAction("Formularz", "SUBMIT_LEAD_FORM", "ENABLED", 5.0)]

    off = assess_measurement_health(actions, ga4_linked=False)
    on = assess_measurement_health(actions, ga4_linked=False, enhanced_conversions_enabled=True)

    assert _by_key(off, "enhanced_conversions").status is MeasurementStatus.NEEDS_ATTENTION
    assert _by_key(on, "enhanced_conversions").status is MeasurementStatus.HEALTHY


def test_value_tracking_healthy_when_economics_configured() -> None:
    actions = [FakeAction("Formularz", "SUBMIT_LEAD_FORM", "ENABLED", 5.0)]

    off = assess_measurement_health(actions, ga4_linked=False)
    on = assess_measurement_health(actions, ga4_linked=False, value_config_present=True)

    assert _by_key(off, "value_tracking").status is MeasurementStatus.NEEDS_ATTENTION
    assert _by_key(on, "value_tracking").status is MeasurementStatus.HEALTHY


def test_consent_mode_v2_healthy_when_detected() -> None:
    actions = [FakeAction("Formularz", "SUBMIT_LEAD_FORM", "ENABLED", 5.0)]

    off = assess_measurement_health(actions, ga4_linked=False)
    on = assess_measurement_health(actions, ga4_linked=False, consent_mode_v2_detected=True)

    assert _by_key(off, "consent_mode_v2").status is MeasurementStatus.NEEDS_ATTENTION
    assert _by_key(on, "consent_mode_v2").status is MeasurementStatus.HEALTHY


def test_actions_present_but_none_receiving_needs_attention() -> None:
    actions = [FakeAction("Stara akcja", "DEFAULT", "ENABLED", 0.0)]

    report = assess_measurement_health(actions, ga4_linked=False)

    assert _by_key(report, "conversion_actions").status is MeasurementStatus.NEEDS_ATTENTION
    assert report.overall_status is MeasurementStatus.NEEDS_ATTENTION
