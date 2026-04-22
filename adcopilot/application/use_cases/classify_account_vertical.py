"""Use case: classify a Google Ads account into a vertical based on snapshot data."""

from __future__ import annotations

from datetime import UTC, datetime

from adcopilot.domain.launch.templates import detect_vertical_from_description
from adcopilot.domain.snapshot import KeywordSnapshot


def _detect_from_keywords(keywords: list[KeywordSnapshot]) -> str | None:
    """Infer vertical from the most frequent keyword terms."""
    if not keywords:
        return None
    # Concatenate all keyword texts into a pseudo-description for detection
    combined = " ".join(kw.text for kw in keywords[:50])
    result = detect_vertical_from_description(combined)
    return result if result != "generic" else None


class ClassifyAccountVerticalUseCase:
    """Classify an account's vertical from its keywords and optional business description.

    Stores vertical + sub_vertical on the account row via the account repository.
    """

    def __init__(self, account_repo: object) -> None:
        self._account_repo = account_repo

    async def run(
        self,
        account_id: str,
        keywords: list[KeywordSnapshot],
        business_description: str = "",
    ) -> str:
        """Classify and persist the vertical; returns the detected vertical string."""
        # Try business description first (most reliable), then keyword fallback
        vertical: str | None = None
        if business_description:
            detected = detect_vertical_from_description(business_description)
            if detected != "generic":
                vertical = detected

        if vertical is None:
            vertical = _detect_from_keywords(keywords)

        if vertical is None:
            vertical = "generic"

        classified_at = datetime.now(UTC)

        if hasattr(self._account_repo, "update_vertical"):
            await self._account_repo.update_vertical(
                account_id=account_id,
                vertical=vertical,
                sub_vertical=None,
                classified_at=classified_at,
            )

        return vertical
