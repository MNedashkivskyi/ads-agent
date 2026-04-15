"""Rule-based validator for ``CampaignProposal`` domain objects.

Checks Google Ads structural limits and budget consistency.
Returns a list of human-readable error messages (empty list = valid).
"""

from __future__ import annotations

from adcopilot.domain.launch.entities import CampaignBrief, CampaignProposal

# ---------------------------------------------------------------------------
# Google Ads RSA / campaign limits
# ---------------------------------------------------------------------------

MAX_HEADLINE_CHARS: int = 30
MAX_DESCRIPTION_CHARS: int = 90
MAX_PATH_CHARS: int = 15
MIN_HEADLINES_PER_AD: int = 3
MIN_DESCRIPTIONS_PER_AD: int = 2
MIN_KEYWORDS_PER_AD_GROUP: int = 8
MAX_KEYWORDS_PER_AD_GROUP: int = 20
MIN_AD_GROUPS: int = 1
MAX_AD_GROUPS: int = 10

# Allow ±5 % drift from the expected daily budget (PLN rounding)
_BUDGET_TOLERANCE = 0.05


def validate_proposal(
    proposal: CampaignProposal,
    brief: CampaignBrief,
) -> list[str]:
    """Return a (possibly empty) list of validation-error messages."""
    errors: list[str] = []

    # ------------------------------------------------------------------
    # Budget check
    # ------------------------------------------------------------------
    expected_daily = int(brief.monthly_budget_pln / 30 * 1_000_000)
    if expected_daily > 0:
        drift = abs(proposal.daily_budget_micros - expected_daily) / expected_daily
        if drift > _BUDGET_TOLERANCE:
            errors.append(
                f"daily_budget_micros {proposal.daily_budget_micros} deviates "
                f"{drift:.1%} from expected {expected_daily} "
                f"(monthly {brief.monthly_budget_pln} PLN / 30)"
            )

    # ------------------------------------------------------------------
    # Ad-group count
    # ------------------------------------------------------------------
    if not proposal.ad_groups:
        errors.append("proposal has no ad groups")
        return errors  # no point checking further

    if len(proposal.ad_groups) > MAX_AD_GROUPS:
        errors.append(
            f"proposal has {len(proposal.ad_groups)} ad groups (max {MAX_AD_GROUPS})"
        )

    # ------------------------------------------------------------------
    # Per-ad-group checks
    # ------------------------------------------------------------------
    for ag in proposal.ad_groups:
        prefix = f"ad_group '{ag.name}'"

        # Keyword count
        kw_count = len(ag.keywords)
        if kw_count < MIN_KEYWORDS_PER_AD_GROUP:
            errors.append(
                f"{prefix}: {kw_count} keywords (min {MIN_KEYWORDS_PER_AD_GROUP})"
            )
        if kw_count > MAX_KEYWORDS_PER_AD_GROUP:
            errors.append(
                f"{prefix}: {kw_count} keywords (max {MAX_KEYWORDS_PER_AD_GROUP})"
            )

        # Ad copy
        if not ag.ads:
            errors.append(f"{prefix}: has no ads")
            continue

        for ad_idx, ad in enumerate(ag.ads):
            ad_prefix = f"{prefix} ad[{ad_idx}]"

            # Headline count
            if len(ad.headlines) < MIN_HEADLINES_PER_AD:
                errors.append(
                    f"{ad_prefix}: {len(ad.headlines)} headlines "
                    f"(min {MIN_HEADLINES_PER_AD})"
                )
            # Headline length
            for hl in ad.headlines:
                if len(hl) > MAX_HEADLINE_CHARS:
                    errors.append(
                        f"{ad_prefix}: headline too long ({len(hl)} chars > "
                        f"{MAX_HEADLINE_CHARS}): '{hl[:35]}'"
                    )

            # Description count
            if len(ad.descriptions) < MIN_DESCRIPTIONS_PER_AD:
                errors.append(
                    f"{ad_prefix}: {len(ad.descriptions)} descriptions "
                    f"(min {MIN_DESCRIPTIONS_PER_AD})"
                )
            # Description length
            for desc in ad.descriptions:
                if len(desc) > MAX_DESCRIPTION_CHARS:
                    errors.append(
                        f"{ad_prefix}: description too long ({len(desc)} chars > "
                        f"{MAX_DESCRIPTION_CHARS}): '{desc[:50]}'"
                    )

            # Path segment lengths
            for seg_idx, seg in enumerate(ad.path_segments):
                if len(seg) > MAX_PATH_CHARS:
                    errors.append(
                        f"{ad_prefix}: path_segment[{seg_idx}] too long "
                        f"({len(seg)} > {MAX_PATH_CHARS}): '{seg}'"
                    )

    return errors
