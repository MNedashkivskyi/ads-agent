"""Check whether an account has macro-conversion tracking configured.

Called after campaign creation. If no macro-conversion actions exist,
returns a guide message so the caller can send it via Telegram.
"""

from __future__ import annotations

from adcopilot.domain.snapshot import ConversionActionSnapshot

_MACRO_CATEGORIES = frozenset({"PURCHASE", "LEAD", "SIGNUP", "PHONE_CALL"})


def has_macro_conversion_tracking(
    conversion_actions: list[ConversionActionSnapshot],
) -> bool:
    """Return True if account has at least one enabled macro-conversion action."""
    return any(
        ca.status == "ENABLED"
        and ca.category in _MACRO_CATEGORIES
        and ca.include_in_conversions_metric
        for ca in conversion_actions
    )
