"""Check whether an account has macro-conversion tracking configured.

Used by the enable-spend gate and the conversion-tracking setup flow.
"""

from __future__ import annotations

from adcopilot.domain.snapshot import ConversionActionSnapshot

_MACRO_CATEGORIES = frozenset({"PURCHASE", "LEAD", "SIGNUP", "PHONE_CALL"})

# Launch goals that require conversion tracking before spend is enabled. A goal
# not in this set (e.g. plain "visit"/traffic) may be enabled without tracking.
_GOALS_REQUIRING_TRACKING = frozenset(
    {"call", "phone_call", "book", "booking", "purchase", "buy", "signup", "sign_up", "lead"}
)


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


def goal_requires_tracking(primary_action: str | None) -> bool:
    """Return True if a campaign goal requires conversion tracking before spend."""
    normalised = (primary_action or "").strip().lower().replace(" ", "_")
    return normalised in _GOALS_REQUIRING_TRACKING
