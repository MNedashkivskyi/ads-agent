"""SH2: PMax target-ROAS executor + adapter boundary + spend-guard tROAS bounds."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from adcopilot.application.executors.adjust_pmax_target_roas import AdjustPmaxTargetRoasExecutor
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.domain.spend_guard import AccountSpendContext, SpendAction, evaluate_spend_action
from adcopilot.domain.spend_safety import SpendSafetyConfig
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations


def _rec() -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id="acc-1",
        kind=RecommendationKind.ADJUST_PMAX_TARGET_ROAS,
        severity=RecommendationSeverity.HIGH,
        target={"campaign_id": 99},
        payload={"campaign_id": 99, "target_roas": 3.0},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=datetime(2026, 6, 3, tzinfo=UTC),
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_executor_calls_set_target_roas() -> None:
    mutations = FakeGoogleAdsMutations()
    result = await AdjustPmaxTargetRoasExecutor().execute(_rec(), mutations, "tok", "123")
    assert result["action"] == "pmax_target_roas_set"
    assert mutations.calls == [
        {"method": "set_target_roas", "customer_id": "123", "campaign_id": 99, "target_roas": 3.0}
    ]


@pytest.mark.asyncio
async def test_adapter_set_target_roas_proto(monkeypatch) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter

    captured: dict = {}

    class FakeCampaignService:
        def campaign_path(self, cid, campaign_id):
            return f"customers/{cid}/campaigns/{campaign_id}"

        def mutate_campaigns(self, customer_id, operations):
            captured["customer_id"] = customer_id
            captured["target_roas"] = operations[0].update.target_roas.target_roas
            return SimpleNamespace(results=[SimpleNamespace(resource_name="x")])

    class FakeClient:
        def get_service(self, name):
            return FakeCampaignService()

        def get_type(self, name):
            return SimpleNamespace(
                update=SimpleNamespace(target_roas=SimpleNamespace()), update_mask=SimpleNamespace()
            )

        def copy_from(self, dst, src):
            pass

    adapter = GoogleAdsMutationsAdapter(Settings())
    monkeypatch.setattr(adapter, "_build_client", lambda rt: FakeClient())
    await adapter.set_target_roas(refresh_token="t", customer_id="123-456", campaign_id=99, target_roas=3.5)
    assert captured["customer_id"] == "123456"
    assert captured["target_roas"] == 3.5


# --- spend guard tROAS ---

def _ctx() -> AccountSpendContext:
    return AccountSpendContext(days_elapsed=15, days_in_month=30)


def test_guard_tightening_troas_allowed() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1, max_budget_increase_pct=50.0)
    action = SpendAction(kind="ADJUST_PMAX_TARGET_ROAS", current_target_roas=2.0, new_target_roas=3.0)
    assert evaluate_spend_action(action, cfg, _ctx()).allowed is True


def test_guard_loosening_troas_within_bound_allowed() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1, max_budget_increase_pct=50.0)
    action = SpendAction(kind="ADJUST_PMAX_TARGET_ROAS", current_target_roas=2.0, new_target_roas=1.5)  # -25%
    assert evaluate_spend_action(action, cfg, _ctx()).allowed is True


def test_guard_loosening_troas_beyond_bound_denied() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1, max_budget_increase_pct=50.0)
    action = SpendAction(kind="ADJUST_PMAX_TARGET_ROAS", current_target_roas=4.0, new_target_roas=1.0)  # -75%
    d = evaluate_spend_action(action, cfg, _ctx())
    assert d.allowed is False
    assert d.code == "TROAS_RELAX"
