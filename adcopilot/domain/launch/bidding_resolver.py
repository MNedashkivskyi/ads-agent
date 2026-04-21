"""Deterministic bidding strategy resolver.

Replaces free LLM bidding-strategy selection with a rule-based resolver that
accounts for budget tier, conversion-tracking status, and existing conversion
volume.  This enforces the industry-standard staged progression:

    No tracking  → MAXIMIZE_CLICKS (no upgrade path)
    MICRO        → MAXIMIZE_CLICKS → (30 conv) → MAXIMIZE_CONVERSIONS
    MID <15 conv → MAXIMIZE_CLICKS → (30 conv) → MAXIMIZE_CONVERSIONS
    MID 15-30    → MAXIMIZE_CONVERSIONS → (50 conv) → TARGET_CPA
    MID 30+      → MAXIMIZE_CONVERSIONS directly
    GROWTH <30   → MAXIMIZE_CONVERSIONS → (50 conv) → TARGET_CPA
    GROWTH 30+   → TARGET_CPA (set at 75 % of account avg CPA)
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.launch.budget_tier import BudgetTier


@dataclass(frozen=True)
class BiddingRecommendation:
    initial_strategy: str
    """Google Ads bidding strategy to use at campaign launch."""

    upgrade_strategy: str | None
    """Strategy to graduate to once *upgrade_threshold_conversions* is reached."""

    upgrade_threshold_conversions: int | None
    """Monthly conversion count that triggers the upgrade recommendation."""

    rationale: str
    """Human-readable explanation of the choice."""


def resolve_bidding_strategy(
    tier: BudgetTier,
    has_conversion_tracking: bool,
    existing_monthly_conversions: float,
) -> BiddingRecommendation:
    """Return the appropriate bidding strategy for a new campaign.

    Args:
        tier: Budget tier of the account.
        has_conversion_tracking: Whether the account has at least one active
            macro-conversion action configured in Google Ads.
        existing_monthly_conversions: Average monthly conversions recorded over
            the last 30 days (0 if the account is brand-new).

    Returns:
        A :class:`BiddingRecommendation` with the resolved strategy and upgrade
        path.
    """
    if not has_conversion_tracking:
        return BiddingRecommendation(
            initial_strategy="MAXIMIZE_CLICKS",
            upgrade_strategy=None,
            upgrade_threshold_conversions=None,
            rationale=(
                "No conversion tracking detected. MAXIMIZE_CLICKS is the only safe "
                "option — Smart Bidding strategies require conversion data to learn. "
                "Set up conversion tracking to unlock MAXIMIZE_CONVERSIONS."
            ),
        )

    if tier == BudgetTier.MICRO:
        return BiddingRecommendation(
            initial_strategy="MAXIMIZE_CLICKS",
            upgrade_strategy="MAXIMIZE_CONVERSIONS",
            upgrade_threshold_conversions=30,
            rationale=(
                "MICRO budget (< 500 PLN/mo). MAXIMIZE_CONVERSIONS needs ≥ 30 "
                "conversions/month to exit the learning phase — unlikely at this "
                "spend level. Start with MAXIMIZE_CLICKS; upgrade once the account "
                "reaches 30 monthly conversions."
            ),
        )

    if tier == BudgetTier.MID:
        if existing_monthly_conversions < 15:
            return BiddingRecommendation(
                initial_strategy="MAXIMIZE_CLICKS",
                upgrade_strategy="MAXIMIZE_CONVERSIONS",
                upgrade_threshold_conversions=30,
                rationale=(
                    "MID budget with < 15 monthly conversions. Insufficient data for "
                    "MAXIMIZE_CONVERSIONS learning phase. Start with MAXIMIZE_CLICKS "
                    "and upgrade at 30 conversions."
                ),
            )
        if existing_monthly_conversions < 30:
            return BiddingRecommendation(
                initial_strategy="MAXIMIZE_CONVERSIONS",
                upgrade_strategy="TARGET_CPA",
                upgrade_threshold_conversions=50,
                rationale=(
                    "MID budget with 15–30 monthly conversions. Enough data to start "
                    "MAXIMIZE_CONVERSIONS. Graduate to TARGET_CPA at 50 conversions "
                    "for tighter cost-per-lead control."
                ),
            )
        # MID with 30+
        return BiddingRecommendation(
            initial_strategy="MAXIMIZE_CONVERSIONS",
            upgrade_strategy="TARGET_CPA",
            upgrade_threshold_conversions=50,
            rationale=(
                "MID budget with 30+ monthly conversions. Start directly with "
                "MAXIMIZE_CONVERSIONS; upgrade to TARGET_CPA at 50 conversions."
            ),
        )

    # GROWTH tier
    if existing_monthly_conversions < 30:
        return BiddingRecommendation(
            initial_strategy="MAXIMIZE_CONVERSIONS",
            upgrade_strategy="TARGET_CPA",
            upgrade_threshold_conversions=50,
            rationale=(
                "GROWTH budget with < 30 monthly conversions. Start with "
                "MAXIMIZE_CONVERSIONS to build conversion history; graduate to "
                "TARGET_CPA at 50 conversions."
            ),
        )
    # GROWTH with 30+
    return BiddingRecommendation(
        initial_strategy="TARGET_CPA",
        upgrade_strategy=None,
        upgrade_threshold_conversions=None,
        rationale=(
            "GROWTH budget with 30+ monthly conversions. Sufficient data for "
            "TARGET_CPA. Set target = 75 % of account average CPA for an "
            "aggressive-but-achievable goal."
        ),
    )
