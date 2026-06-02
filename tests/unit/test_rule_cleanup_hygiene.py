"""Phase 2: correctness/hygiene.

- rule_54 no longer maps a "device campaign split" to the device-bid executor.
- duplicate-kind dedup relies on a stable target_hash.
"""

from __future__ import annotations

from adcopilot.application.detection.rules.rule_54_device_campaign_split import (
    DeviceCampaignSplitRule,
)
from adcopilot.domain.recommendation import (
    NON_EXECUTABLE_KINDS,
    RecommendationKind,
    compute_target_hash,
)


def test_rule54_is_advisory_not_a_bid_mutation() -> None:
    # Approving it must NOT run the device-bid executor (wrong action bug).
    assert DeviceCampaignSplitRule.kind is RecommendationKind.DEVICE_CAMPAIGN_SPLIT
    assert RecommendationKind.DEVICE_CAMPAIGN_SPLIT in NON_EXECUTABLE_KINDS
    # The real device-bid action stays executable for the legitimate rule (28).
    assert RecommendationKind.DEVICE_BID_ADJUSTMENT not in NON_EXECUTABLE_KINDS


def test_dead_audience_executor_removed() -> None:
    import importlib.util

    assert (
        importlib.util.find_spec("adcopilot.application.executors.audience_bid_adjustment") is None
    )


def test_target_hash_dedups_same_target() -> None:
    # Two rules emitting the same kind for the same target produce the same hash,
    # so list_active_dedup_keys collapses them — no duplicate card to the user.
    t = {"campaign_id": 1, "ad_group_id": 10}
    assert compute_target_hash(t) == compute_target_hash(dict(reversed(list(t.items()))))
    assert compute_target_hash(t) != compute_target_hash({"campaign_id": 2, "ad_group_id": 10})
