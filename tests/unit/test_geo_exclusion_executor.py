"""Tests for GeoExclusionExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.geo_exclusion import GeoExclusionExecutor
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations

_NOW = datetime(2026, 4, 10, tzinfo=UTC)


def _rec(target: dict) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=AccountId("acct-1"),
        kind=RecommendationKind.GEO_EXCLUSION,
        severity=RecommendationSeverity.HIGH,
        target=target,
        payload={},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_executor_excludes_geo() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec({"campaign_id": "100", "location_id": "9067762"})
    result = await GeoExclusionExecutor().execute(rec, mutations, "token", "cid")

    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "exclude_geo_location"
    assert call["campaign_id"] == 100
    assert call["location_id"] == 9067762
    assert result["action"] == "geo_excluded"


@pytest.mark.asyncio
async def test_missing_location_id_raises() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec({"campaign_id": "100"})
    with pytest.raises(KeyError):
        await GeoExclusionExecutor().execute(rec, mutations, "token", "cid")


def test_geo_exclusion_removed_from_non_executable() -> None:
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS

    assert RecommendationKind.GEO_EXCLUSION not in NON_EXECUTABLE_KINDS
