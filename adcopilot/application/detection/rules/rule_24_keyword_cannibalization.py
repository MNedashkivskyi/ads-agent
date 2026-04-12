"""Detection rule: same keyword text appears in multiple ad groups (cannibalization)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

# Keywords in these statuses compete with each other for auction budget
_ACTIVE_STATUSES = {"ENABLED", "PAUSED"}


class KeywordCannibalizationRule:
    kind = RecommendationKind.KEYWORD_CANNIBALIZATION
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Build ad group info lookup: ad_group_id -> (name, campaign_id)
        ag_info: dict[int, tuple[str, int]] = {
            ag.ad_group_id: (ag.name, ag.campaign_id) for ag in ctx.ad_groups
        }

        # Group (ad_group_id, campaign_id) pairs by normalised keyword text
        # Use a set to deduplicate multiple match types for the same text in the same group
        text_to_ad_groups: dict[str, set[int]] = defaultdict(set)
        for kw in ctx.keywords:
            if kw.status not in _ACTIVE_STATUSES:
                continue
            normalised = kw.text.lower().strip()
            text_to_ad_groups[normalised].add(kw.ad_group_id)

        recs: list[Recommendation] = []
        seen_targets: set[tuple[int, str]] = set()

        for normalised_text, ad_group_ids in text_to_ad_groups.items():
            if len(ad_group_ids) < 2:
                continue

            conflicting = sorted(ad_group_ids)

            for ag_id in conflicting:
                dedup_key = (ag_id, normalised_text)
                if dedup_key in seen_targets:
                    continue
                seen_targets.add(dedup_key)

                ag_name, campaign_id = ag_info.get(ag_id, ("", 0))
                other_ag_ids = [x for x in conflicting if x != ag_id]

                target = {
                    "ad_group_id": ag_id,
                    "campaign_id": campaign_id,
                    "keyword_text": normalised_text,
                }
                evidence = {
                    "keyword_text": normalised_text,
                    "ad_group_name": ag_name,
                    "conflicting_ad_group_ids": other_ag_ids,
                    "duplicate_count": len(conflicting),
                }
                recs.append(
                    Recommendation(
                        id=RecommendationId(str(uuid.uuid4())),
                        account_id=ctx.account.id,  # type: ignore[arg-type]
                        kind=self.kind,
                        severity=self.severity,
                        target=target,
                        payload={
                            "ad_group_id": ag_id,
                            "campaign_id": campaign_id,
                            "keyword_text": normalised_text,
                        },
                        evidence=evidence,
                        estimated_monthly_savings_micros=0,
                        created_at=datetime.now(tz=UTC),
                        status=RecommendationStatus.PENDING,
                    )
                )

        return recs
