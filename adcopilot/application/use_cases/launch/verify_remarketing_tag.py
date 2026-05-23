"""VerifyRemarketingTagUseCase — check if the remarketing tag is active."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class VerifyRemarketingTagUseCase:
    """Check whether the Google Ads remarketing tag is active for an account.

    Called when the user replies "done" to the remarketing setup guide.
    Queries the user_list resource to confirm the global site tag is firing
    and at least one audience list is populating.
    """

    def __init__(self, queries_adapter) -> None:
        self._queries = queries_adapter

    async def execute(
        self,
        refresh_token: str,
        customer_id: str,
    ) -> tuple[bool, str]:
        """Return (tag_active, message) where message is a Telegram-ready reply."""
        try:
            lists = await self._queries.query_remarketing_lists(refresh_token, customer_id)
        except Exception as exc:
            logger.warning("remarketing_lists_query_failed", error=str(exc)[:100])
            return False, (
                "⚠️ I couldn't check your tag status right now\\. "
                "Please wait a few minutes and try again\\."
            )

        if not lists:
            return False, (
                "❌ No remarketing lists found yet\\.\n\n"
                "It can take up to 24 hours for the tag to appear after installation\\. "
                "Make sure you pasted the tag in *every page* of your website "
                "\\(ideally via Google Tag Manager\\)\\. Try again tomorrow\\."
            )

        populating = [lst for lst in lists if lst.member_count > 0]
        if populating:
            total = sum(lst.member_count for lst in populating)
            return True, (
                f"✅ *Remarketing tag is active\\!*\n\n"
                f"Your lists are already collecting data: *{total:,} visitors* tracked so far\\.\n\n"
                "Once a list reaches 1,000\\+ users, I'll recommend adding a remarketing campaign "
                "to re\\-engage your past visitors\\."
            )

        return True, (
            "✅ *Tag detected\\!* Your lists are being created but are still populating\\.\\.\\.\\.\n\n"
            "Come back in 7\\+ days once visitors have accumulated\\. "
            "I'll notify you when you're eligible for remarketing campaigns\\."
        )
