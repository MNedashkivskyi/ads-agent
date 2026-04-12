"""Detection rule: a negative keyword is blocking a positive keyword in the same campaign/ad group."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


def _tokenise(text: str) -> set[str]:
    return set(text.lower().split())


def _is_blocked(kw_text: str, neg_text: str, neg_match_type: str) -> bool:
    """Return True if the negative keyword blocks the positive keyword."""
    kw_lower = kw_text.lower()
    neg_lower = neg_text.lower()
    match neg_match_type:
        case "EXACT":
            return kw_lower == neg_lower
        case "PHRASE":
            return neg_lower in kw_lower
        case "BROAD":
            # All tokens of the negative must be present in the positive keyword tokens
            neg_tokens = _tokenise(neg_lower)
            kw_tokens = _tokenise(kw_lower)
            return neg_tokens.issubset(kw_tokens)
        case _:
            return False


class NegativeKeywordConflictRule:
    kind = RecommendationKind.NEGATIVE_KEYWORD_CONFLICT
    severity = RecommendationSeverity.CRITICAL

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.negative_keywords:
            return []

        # Build campaign_id lookup from ad groups: ad_group_id -> campaign_id
        ag_campaign: dict[int, int] = {
            ag.ad_group_id: ag.campaign_id for ag in ctx.ad_groups
        }

        recs: list[Recommendation] = []
        # Track seen conflicts to emit at most one rec per positive keyword
        seen_criterion_ids: set[int] = set()

        for kw in ctx.keywords:
            if kw.status != "ENABLED":
                continue
            if kw.criterion_id in seen_criterion_ids:
                continue

            campaign_id = ag_campaign.get(kw.ad_group_id, 0)

            for neg in ctx.negative_keywords:
                # Scope check: campaign-level or ad-group-level conflict
                is_campaign_level = neg.ad_group_id == 0 and neg.campaign_id == campaign_id
                is_ag_level = neg.ad_group_id != 0 and neg.ad_group_id == kw.ad_group_id

                if not (is_campaign_level or is_ag_level):
                    continue

                if not _is_blocked(kw.text, neg.text, neg.match_type):
                    continue

                seen_criterion_ids.add(kw.criterion_id)
                target = {
                    "ad_group_id": kw.ad_group_id,
                    "campaign_id": campaign_id,
                    "criterion_id": kw.criterion_id,
                }
                evidence = {
                    "keyword_text": kw.text,
                    "keyword_match_type": kw.match_type,
                    "negative_text": neg.text,
                    "negative_match_type": neg.match_type,
                    "conflict_scope": "CAMPAIGN" if is_campaign_level else "AD_GROUP",
                }
                recs.append(
                    Recommendation(
                        id=RecommendationId(str(uuid.uuid4())),
                        account_id=ctx.account.id,  # type: ignore[arg-type]
                        kind=self.kind,
                        severity=self.severity,
                        target=target,
                        payload={
                            "criterion_id": kw.criterion_id,
                            "ad_group_id": kw.ad_group_id,
                            "campaign_id": campaign_id,
                        },
                        evidence=evidence,
                        # Estimate: current keyword cost is being wasted monthly
                        estimated_monthly_savings_micros=kw.cost_micros * 4,
                        created_at=datetime.now(tz=UTC),
                        status=RecommendationStatus.PENDING,
                    )
                )
                break  # one rec per positive keyword — stop checking negatives

        return recs
