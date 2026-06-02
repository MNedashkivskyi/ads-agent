from __future__ import annotations

from types import SimpleNamespace

from adcopilot.application.ports.measurement import UploadResult
from adcopilot.infrastructure.google_ads.measurement_mutations_adapter import (
    GoogleAdsMeasurementUploadAdapter as Adapter,
)


def _ok_result():
    return SimpleNamespace(
        conversion_action="customers/1/conversionActions/9",
        gclid="GCL",
        gbraid="",
        wbraid="",
        conversion_date_time="2026-06-01 00:00:00+00:00",
    )


def _empty_result():
    # Google returns an empty result message at the index of a failed operation.
    return SimpleNamespace(
        conversion_action="", gclid="", gbraid="", wbraid="", conversion_date_time=""
    )


def test_upload_result_math() -> None:
    r = UploadResult.build(received=5, succeeded=3, errors=["boom"], validate_only=False)
    assert r.received == 5
    assert r.succeeded == 3
    assert r.failed == 2
    assert r.errors == ["boom"]


def test_interpret_all_success() -> None:
    resp = SimpleNamespace(
        results=[_ok_result(), _ok_result()],
        partial_failure_error=SimpleNamespace(code=0, message="", details=[]),
    )
    r = Adapter._interpret(resp, received=2, validate_only=True)
    assert (r.received, r.succeeded, r.failed) == (2, 2, 0)
    assert r.errors == []
    assert r.validate_only is True


def test_interpret_partial_failure_counts_and_surfaces_message() -> None:
    resp = SimpleNamespace(
        results=[_ok_result(), _empty_result()],
        partial_failure_error=SimpleNamespace(
            code=3, message="1 error: invalid gclid", details=[]
        ),
    )
    r = Adapter._interpret(resp, received=2, validate_only=False)
    assert r.succeeded == 1
    assert r.failed == 1
    assert any("invalid gclid" in e for e in r.errors)


def _adjustment_result():
    # Adjustment results echo conversion_action + order_id (no gclid).
    return SimpleNamespace(
        conversion_action="customers/1/conversionActions/9",
        gclid="",
        gbraid="",
        wbraid="",
        order_id="crm-1",
    )


def test_interpret_handles_adjustment_results() -> None:
    resp = SimpleNamespace(
        results=[_adjustment_result(), _adjustment_result()],
        partial_failure_error=SimpleNamespace(code=0, message="", details=[]),
    )
    r = Adapter._interpret(resp, received=2, validate_only=True)
    assert (r.received, r.succeeded, r.failed) == (2, 2, 0)


def test_interpret_no_results_no_error() -> None:
    resp = SimpleNamespace(results=[], partial_failure_error=SimpleNamespace(code=0, message="", details=[]))
    r = Adapter._interpret(resp, received=0, validate_only=False)
    assert (r.received, r.succeeded, r.failed) == (0, 0, 0)
