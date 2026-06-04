"""Tests for GoogleAdsExperimentAdapter.get_experiment_metrics.

Drives the real method with a fake GoogleAdsService whose `search` returns arm
rows then per-campaign metric rows, closing the causal-experiment evaluation loop
(previously a NotImplementedError).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from adcopilot.infrastructure.google_ads.experiment_mutations_adapter import (
    GoogleAdsExperimentAdapter,
)


def _arm_row(*, control: bool, campaign_ids: list[int]) -> SimpleNamespace:
    return SimpleNamespace(
        experiment_arm=SimpleNamespace(
            control=control,
            campaigns=[f"customers/123/campaigns/{cid}" for cid in campaign_ids],
        )
    )


def _metric_row(campaign_id: int, **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        campaign=SimpleNamespace(id=campaign_id),
        metrics=SimpleNamespace(**metrics),
    )


class _FakeGA:
    def __init__(self, arm_rows, metric_rows):
        self._arm_rows = arm_rows
        self._metric_rows = metric_rows
        self.queries: list[str] = []

    def search(self, customer_id, query):  # noqa: ARG002 - mirror SDK signature
        self.queries.append(query)
        return self._arm_rows if "experiment_arm" in query else self._metric_rows


class _FakeClient:
    def __init__(self, ga):
        self._ga = ga

    def get_service(self, name):  # noqa: ARG002
        return self._ga


def _adapter_with(ga: _FakeGA) -> GoogleAdsExperimentAdapter:
    adapter = GoogleAdsExperimentAdapter(MagicMock())
    adapter._build_client = lambda refresh_token: _FakeClient(ga)  # type: ignore[method-assign]
    return adapter


@pytest.mark.asyncio
async def test_returns_split_metrics_when_both_arms_live():
    ga = _FakeGA(
        arm_rows=[
            _arm_row(control=True, campaign_ids=[100]),
            _arm_row(control=False, campaign_ids=[200]),
        ],
        metric_rows=[
            _metric_row(
                100,
                impressions=5000,
                clicks=250,
                cost_micros=1_000_000,
                conversions=40.0,
                conversions_value=4000.0,
            ),
            _metric_row(
                200,
                impressions=5100,
                clicks=300,
                cost_micros=1_100_000,
                conversions=60.0,
                conversions_value=7200.0,
            ),
        ],
    )
    adapter = _adapter_with(ga)

    metrics = await adapter.get_experiment_metrics(
        "rt", "123-456-7890", "customers/123/experiments/9"
    )

    assert metrics.control["conversions"] == 40.0
    assert metrics.treatment["conversions"] == 60.0
    # Two queries issued: arms first, then per-campaign metrics scoped to both IDs.
    assert "experiment_arm" in ga.queries[0]
    assert "campaign.id IN (100, 200)" in ga.queries[1]


@pytest.mark.asyncio
async def test_pending_when_treatment_campaign_not_materialised():
    ga = _FakeGA(
        arm_rows=[
            _arm_row(control=True, campaign_ids=[100]),
            _arm_row(control=False, campaign_ids=[]),  # treatment not created yet
        ],
        metric_rows=[],
    )
    adapter = _adapter_with(ga)

    metrics = await adapter.get_experiment_metrics("rt", "123", "customers/123/experiments/9")

    assert metrics.status == "PENDING"
    assert metrics.control == {}
    assert metrics.treatment == {}
    # Metrics query must not be issued when arms aren't resolved.
    assert len(ga.queries) == 1


@pytest.mark.asyncio
async def test_missing_metric_row_yields_empty_arm():
    ga = _FakeGA(
        arm_rows=[
            _arm_row(control=True, campaign_ids=[100]),
            _arm_row(control=False, campaign_ids=[200]),
        ],
        metric_rows=[
            _metric_row(
                100, impressions=10, clicks=1, cost_micros=0, conversions=1.0, conversions_value=0.0
            ),
        ],  # treatment campaign 200 returned no metrics
    )
    adapter = _adapter_with(ga)

    metrics = await adapter.get_experiment_metrics("rt", "123", "customers/123/experiments/9")

    assert metrics.control["impressions"] == 10
    assert metrics.treatment == {}
