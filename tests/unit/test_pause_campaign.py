"""SS2: PauseCampaignExecutor + adapter pause_campaign boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from adcopilot.application.executors.pause_campaign import PauseCampaignExecutor
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations


def _rec(target: dict | None = None, payload: dict | None = None) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id="acct-1",
        kind=RecommendationKind.PAUSE_CAMPAIGN,
        severity=RecommendationSeverity.CRITICAL,
        target=target or {},
        payload=payload or {},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=datetime(2026, 6, 3, tzinfo=UTC),
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_executor_calls_pause_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    result = await PauseCampaignExecutor().execute(
        _rec(target={"campaign_id": 777}), mutations, "tok", "123-456-7890"
    )
    assert result == {"campaign_id": 777, "action": "campaign_paused"}
    assert mutations.calls == [
        {"method": "pause_campaign", "customer_id": "123-456-7890", "campaign_id": 777}
    ]


@pytest.mark.asyncio
async def test_executor_reads_campaign_id_from_payload_fallback() -> None:
    mutations = FakeGoogleAdsMutations()
    await PauseCampaignExecutor().execute(_rec(payload={"campaign_id": 99}), mutations, "tok", "1")
    assert mutations.calls[0]["campaign_id"] == 99


@pytest.mark.asyncio
async def test_adapter_pause_sets_status_paused(monkeypatch) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter

    captured: dict = {}

    class FakeEnums:
        class CampaignStatusEnum:
            PAUSED = "PAUSED"

    class FakeCampaignService:
        def campaign_path(self, cid, campaign_id):
            return f"customers/{cid}/campaigns/{campaign_id}"

        def mutate_campaigns(self, customer_id, operations):
            captured["customer_id"] = customer_id
            captured["status"] = operations[0].update.status
            captured["resource_name"] = operations[0].update.resource_name
            return SimpleNamespace(results=[SimpleNamespace(resource_name="x")])

    class FakeClient:
        enums = FakeEnums()

        def get_service(self, name):
            assert name == "CampaignService"
            return FakeCampaignService()

        def get_type(self, name):
            return SimpleNamespace(update=SimpleNamespace(), update_mask=SimpleNamespace())

        def copy_from(self, dst, src):
            pass

    adapter = GoogleAdsMutationsAdapter(Settings())
    monkeypatch.setattr(adapter, "_build_client", lambda rt: FakeClient())

    await adapter.pause_campaign(refresh_token="tok", customer_id="123-456-7890", campaign_id=42)

    assert captured["customer_id"] == "1234567890"
    assert captured["status"] == "PAUSED"
    assert captured["resource_name"].endswith("/campaigns/42")
