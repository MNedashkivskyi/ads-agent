"""Detection rule 57 — Customer Match Lookalike Opportunity.

Fires when a customer match list has more than 1 000 members but no similar
(lookalike) audience has been created from it.  A large seed list is a strong
signal that a lookalike expansion would meaningfully grow reach.
"""

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

_MIN_LIST_MEMBERS = 1_000


class CustomerMatchLookalikeRule:
    kind = RecommendationKind.AUDIENCE_EXPANSION
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # ctx.customer_match_lists is a list of objects with attributes:
        #   user_list_id, name, member_count, has_similar_audience (bool)
        customer_match_lists = getattr(ctx, "customer_match_lists", None)
        if not customer_match_lists:
            return []

        recommendations: list[Recommendation] = []
        for lst in customer_match_lists:
            member_count = getattr(lst, "member_count", 0) or 0
            has_similar = getattr(lst, "has_similar_audience", False)
            user_list_id = getattr(lst, "user_list_id", None)
            list_name = getattr(lst, "name", str(user_list_id))

            if member_count < _MIN_LIST_MEMBERS:
                continue
            if has_similar:
                continue

            target = {
                "account_id": str(ctx.account.id),
                "user_list_id": str(user_list_id),
            }
            payload = {
                "user_list_id": user_list_id,
                "list_name": list_name,
                "member_count": member_count,
                "description_pl": (
                    f"Lista dopasowania klientow '{list_name}' zawiera {member_count:,} "
                    "kontaktow, ale nie utworzono dla niej listy podobnych odbiorcow. "
                    "Przy tak duzej liscie wyjsciowej podobna lista moze znaczaco poszerzyc zasieg "
                    "przy zachowaniu wysokiej jakosci ruchu."
                ),
                "recommendation_pl": (
                    "Przejdz do Menedzera odbiorcow Google Ads i utworz liste podobnych "
                    f"odbiorcow na bazie listy '{list_name}'. Nastepnie dodaj ja jako sygnal "
                    "do kampanii Performance Max lub jako targetowanie z modyfikatorem stawki "
                    "w kampaniach Search/Display."
                ),
            }
            evidence = {
                "user_list_id": user_list_id,
                "list_name": list_name,
                "member_count": member_count,
                "has_similar_audience": False,
            }
            recommendations.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recommendations
