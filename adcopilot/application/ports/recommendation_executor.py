"""RecommendationExecutor port (Protocol)."""

from __future__ import annotations

from typing import Any, Protocol

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class RecommendationExecutor(Protocol):
    kind: RecommendationKind

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]: ...
