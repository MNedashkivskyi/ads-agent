from __future__ import annotations

from types import SimpleNamespace

from adcopilot.infrastructure.google_ads.experiment_mutations_adapter import _parse_metrics


def _row(campaign_id: int, **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        campaign=SimpleNamespace(id=campaign_id),
        metrics=SimpleNamespace(**metrics),
    )


def test_parse_metrics_splits_control_and_treatment() -> None:
    rows = [
        _row(100, impressions=5000, clicks=250, cost_micros=1_000_000, conversions=40.0, conversions_value=4000.0),
        _row(200, impressions=5100, clicks=300, cost_micros=1_100_000, conversions=60.0, conversions_value=7200.0),
    ]
    result = _parse_metrics(rows, control_campaign_id=100, treatment_campaign_id=200)

    assert result.control["conversions"] == 40.0
    assert result.control["clicks"] == 250
    assert result.treatment["conversions"] == 60.0
    assert result.treatment["conversions_value"] == 7200.0


def test_parse_metrics_ignores_unrelated_campaigns() -> None:
    rows = [
        _row(100, impressions=10, clicks=1, cost_micros=0, conversions=1.0, conversions_value=0.0),
        _row(999, impressions=9999, clicks=999, cost_micros=0, conversions=99.0, conversions_value=0.0),
    ]
    result = _parse_metrics(rows, control_campaign_id=100, treatment_campaign_id=200)

    assert result.control["impressions"] == 10
    assert result.treatment == {}  # 200 absent → empty, 999 ignored


def test_parse_metrics_handles_missing_metric_fields() -> None:
    # Rows from GAQL may omit some metric attrs; parser must default them.
    rows = [_row(100, impressions=5)]
    result = _parse_metrics(rows, control_campaign_id=100, treatment_campaign_id=200)

    assert result.control["impressions"] == 5
    assert result.control["conversions"] == 0.0
    assert result.control["cost_micros"] == 0
