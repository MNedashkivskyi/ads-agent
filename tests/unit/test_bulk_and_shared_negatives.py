"""Tests for bulk execution + shared negative lists (Tier-3 Phase 4)."""

from __future__ import annotations

import pytest

from adcopilot.application.use_cases.execute_recommendations_bulk import (
    BulkExecuteRecommendationsUseCase,
)
from adcopilot.domain.recommendation import RecommendationId
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations

# --------------------------------------------------------------------------- #
# Bulk execution: per-item failure isolation
# --------------------------------------------------------------------------- #


class _Single:
    def __init__(self, fail_on: set[str]) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []

    async def execute(self, rec_id: RecommendationId) -> dict:
        self.calls.append(str(rec_id))
        if str(rec_id) in self.fail_on:
            raise RuntimeError("boom")
        return {"ok": True}


@pytest.mark.asyncio
async def test_bulk_isolates_failures_and_counts():
    single = _Single(fail_on={"b"})
    bulk = BulkExecuteRecommendationsUseCase(single)

    result = await bulk.execute([RecommendationId(x) for x in ["a", "b", "c"]])

    assert result.total == 3
    assert result.succeeded == 2
    assert result.failed == 1
    assert single.calls == ["a", "b", "c"]  # one failure didn't stop the rest
    failed = [r for r in result.results if not r["ok"]]
    assert failed[0]["recommendation_id"] == "b"
    assert "boom" in failed[0]["error"]


@pytest.mark.asyncio
async def test_bulk_empty():
    result = await BulkExecuteRecommendationsUseCase(_Single(set())).execute([])
    assert result.total == 0
    assert result.succeeded == 0


# --------------------------------------------------------------------------- #
# Shared negative-keyword list port (via the fake)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_shared_negative_list_flow_through_fake():
    fake = FakeGoogleAdsMutations()

    ss_id = await fake.create_shared_negative_list("rt", "123", name="Account negatives")
    assert ss_id == 7777

    added = await fake.add_shared_negatives(
        "rt", "123", shared_set_id=ss_id, keywords=[("darmowy", "PHRASE"), ("praca", "EXACT")]
    )
    assert added == 2

    await fake.attach_shared_set_to_campaign("rt", "123", campaign_id=55, shared_set_id=ss_id)

    methods = [c["method"] for c in fake.calls]
    assert methods == [
        "create_shared_negative_list",
        "add_shared_negatives",
        "attach_shared_set_to_campaign",
    ]
    attach = next(c for c in fake.calls if c["method"] == "attach_shared_set_to_campaign")
    assert attach["campaign_id"] == 55
    assert attach["shared_set_id"] == 7777
