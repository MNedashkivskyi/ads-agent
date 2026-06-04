"""Select the LLM model by budget tier.

High-spend (GROWTH) accounts justify a stronger, costlier model for the
highest-leverage generation stage (ad copy); everyone else uses the default.
Pure function — the model strings come from settings, never hardcoded here.
"""

from __future__ import annotations

from adcopilot.domain.launch.budget_tier import BudgetTier


def model_for_tier(tier: BudgetTier, *, default: str, premium: str) -> str:
    """Return the premium model for GROWTH, the default model otherwise."""
    return premium if tier is BudgetTier.GROWTH else default
