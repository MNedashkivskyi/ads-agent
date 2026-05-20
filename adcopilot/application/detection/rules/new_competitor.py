"""Rule — New Competitor.

Fires when a competitor domain appears in the Auction Insights report for the
current snapshot week but was absent 14 days ago (two snapshot cycles back).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


class NewCompetitorRule:
    kind = RecommendationKind.NEW_COMPETITOR
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.auction_insights:
            return []

        cutoff = ctx.snapshot_date - timedelta(days=7)
        recent_domains: dict[int, set[str]] = {}
        old_domains: dict[int, set[str]] = {}

        for row in ctx.auction_insights:
            cid = row["campaign_id"]
            domain = row["competitor_domain"]
            if row["snapshot_date"] >= cutoff:
                recent_domains.setdefault(cid, set()).add(domain)
            else:
                old_domains.setdefault(cid, set()).add(domain)

        recs: list[Recommendation] = []
        for cid, new_set in recent_domains.items():
            previous = old_domains.get(cid, set())
            brand_new = new_set - previous
            if not brand_new:
                continue

            # Find latest impression share for the new domains
            for domain in brand_new:
                latest = next(
                    (
                        r
                        for r in sorted(
                            ctx.auction_insights, key=lambda x: x["snapshot_date"], reverse=True
                        )
                        if r["campaign_id"] == cid and r["competitor_domain"] == domain
                    ),
                    None,
                )
                impression_share = latest["impression_share"] if latest else None

                recs.append(
                    Recommendation(
                        id=RecommendationId(str(uuid.uuid4())),
                        account_id=ctx.account.id,  # type: ignore[arg-type]
                        kind=self.kind,
                        severity=self.severity,
                        target={"campaign_id": cid, "competitor_domain": domain},
                        payload={
                            "campaign_id": cid,
                            "competitor_domain": domain,
                            "impression_share": impression_share,
                        },
                        evidence={
                            "competitor_domain": domain,
                            "impression_share": impression_share,
                            "first_seen": ctx.snapshot_date.isoformat(),
                        },
                        estimated_monthly_savings_micros=0,
                        created_at=datetime.now(tz=UTC),
                        status=RecommendationStatus.PENDING,
                    )
                )

        return recs
