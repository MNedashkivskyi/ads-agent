"""Rule-based validator for ``CampaignProposal`` domain objects.

Checks Google Ads structural limits and budget consistency.
Returns a list of human-readable error messages (empty list = valid).
"""

from __future__ import annotations

from adcopilot.domain.launch.budget_tier import classify_budget_tier
from adcopilot.domain.launch.entities import CampaignBrief, CampaignProposal
from adcopilot.domain.launch.structure_rules import get_structure_config

# ---------------------------------------------------------------------------
# Google Ads RSA / campaign limits (absolute hard limits)
# ---------------------------------------------------------------------------

MAX_HEADLINE_CHARS: int = 30
MAX_DESCRIPTION_CHARS: int = 90
MAX_PATH_CHARS: int = 15
MIN_HEADLINES_PER_AD: int = 3
MIN_DESCRIPTIONS_PER_AD: int = 2
# Keyword count defaults — overridden per-tier in validate_proposal()
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

    # Resolve tier-specific keyword count limits
    tier = classify_budget_tier(brief.monthly_budget_pln)
    tier_cfg = get_structure_config(tier)
    min_kw = tier_cfg.min_keywords_per_group
    max_kw = tier_cfg.max_keywords_per_group

    # ------------------------------------------------------------------
    # Budget check
    # ------------------------------------------------------------------
    base_expected = int(brief.monthly_budget_pln / 30 * 1_000_000)
    # The pipeline intentionally scales daily budget by the vertical's
    # seasonal multiplier (see ``_apply_seasonal_multiplier``). Compare
    # against the adjusted expected value so valid proposals aren't
    # rejected in non-neutral months.
    multiplier = proposal.seasonal_multiplier or 1.0
    expected_daily = int(base_expected * multiplier)
    if expected_daily > 0:
        drift = abs(proposal.daily_budget_micros - expected_daily) / expected_daily
        if drift > _BUDGET_TOLERANCE:
            errors.append(
                f"daily_budget_micros {proposal.daily_budget_micros} deviates "
                f"{drift:.1%} from expected {expected_daily} "
                f"(monthly {brief.monthly_budget_pln} PLN / 30 × seasonal {multiplier:.2f})"
            )

    # ------------------------------------------------------------------
    # Ad-group count
    # ------------------------------------------------------------------
    if not proposal.ad_groups:
        errors.append("proposal has no ad groups")
        return errors  # no point checking further

    if len(proposal.ad_groups) > MAX_AD_GROUPS:
        errors.append(f"proposal has {len(proposal.ad_groups)} ad groups (max {MAX_AD_GROUPS})")

    # ------------------------------------------------------------------
    # Per-ad-group checks
    # ------------------------------------------------------------------
    for ag in proposal.ad_groups:
        prefix = f"ad_group '{ag.name}'"

        # Keyword count — tier-dependent limits
        kw_count = len(ag.keywords)
        if kw_count < min_kw:
            errors.append(f"{prefix}: {kw_count} keywords (min {min_kw} for {tier} tier)")
        if kw_count > max_kw:
            errors.append(f"{prefix}: {kw_count} keywords (max {max_kw} for {tier} tier)")

        # Ad copy
        if not ag.ads:
            errors.append(f"{prefix}: has no ads")
            continue

        for ad_idx, ad in enumerate(ag.ads):
            ad_prefix = f"{prefix} ad[{ad_idx}]"

            # Headline count
            if len(ad.headlines) < MIN_HEADLINES_PER_AD:
                errors.append(
                    f"{ad_prefix}: {len(ad.headlines)} headlines (min {MIN_HEADLINES_PER_AD})"
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

    # ------------------------------------------------------------------
    # Extension character-limit checks (soft — only if extensions present)
    # ------------------------------------------------------------------
    for sl in proposal.sitelinks:
        if len(sl.link_text) > 25:
            errors.append(
                f"sitelink link_text too long ({len(sl.link_text)} > 25): '{sl.link_text}'"
            )
        if len(sl.description1) > 35:
            errors.append(f"sitelink description1 too long ({len(sl.description1)} > 35)")
        if len(sl.description2) > 35:
            errors.append(f"sitelink description2 too long ({len(sl.description2)} > 35)")

    for co in proposal.callouts:
        if len(co.text) > 25:
            errors.append(f"callout text too long ({len(co.text)} > 25): '{co.text}'")

    for sn in proposal.structured_snippets:
        for v in sn.values:
            if len(v) > 25:
                errors.append(f"structured_snippet value too long ({len(v)} > 25): '{v}'")

    return errors
