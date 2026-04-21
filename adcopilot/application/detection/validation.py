"""ValidateProposal — strict pre-launch validation for CampaignProposal.

All 8 rules must pass before a proposal can be promoted to APPROVED and
sent to Google Ads.  A ``ValidationResult`` with ``passed=False`` blocks
the launch and its ``errors`` list is fed back to the LLM for a retry.

Rules
-----
1.  Budget           — daily_budget_micros == monthly_budget_pln / 30 ± 5 %
2.  Protected KWs    — no competitor brands, Adept customer domains,
                       or common trademark terms
3.  Keyword count    — every ad group has 3–15 keywords (inclusive)
4.  Negatives        — must include Adept standard list + vertical-specific
                       terms + user-specified exclusions
5.  Ad copy          — each ad: ≥ 3 headlines ≤ 30 chars, ≥ 2 descriptions
                       ≤ 90 chars, path segments ≤ 15 chars each
6.  Landing page     — final_url must be HTTPS, respond 200 OK within 5 s,
                       and contain the user's language code in content
7.  Bidding          — if account has no active conversion tracking →
                       strategy must be MAXIMIZE_CLICKS
8.  Geographic       — location_targeting must be within (not wider than)
                       the country/region stated in CampaignBrief.location

Architecture
------------
Each rule is a separate module-level function with signature::

    def _rule_N(
        proposal: CampaignProposal,
        brief: CampaignBrief,
        ctx: ValidationContext,
    ) -> list[str]

``validate_proposal`` runs all rules, concatenates errors, and returns a
``ValidationResult``.  The context object carries optional external data
(landing-page check result, conversion-tracking status, …) so the rules
themselves stay pure and easily unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from adcopilot.domain.launch.entities import CampaignBrief, CampaignProposal
from adcopilot.domain.polish_market.negative_keywords import (
    POLISH_STANDARD_NEGATIVES,
    VERTICAL_NEGATIVES_PL,
)

# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of ``validate_proposal``.

    Attributes
    ----------
    passed
        ``True`` only when *all* rules produced zero errors.
    errors
        Ordered list of specific, actionable error messages — one entry per
        failing check.  Empty when ``passed`` is ``True``.
    rule_results
        Mapping of rule name → list of errors for that rule.  Useful for
        targeted LLM feedback (only include errors for failing rules).
    """

    passed: bool
    errors: list[str]
    rule_results: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation context (carries external-system data so rules stay pure)
# ---------------------------------------------------------------------------


@dataclass
class LandingPageCheckResult:
    """Outcome of a landing-page HTTP probe (Rule 6).

    Supply a ``LandingPageChecker`` implementation (or a test fake) and call
    ``ValidationContext.with_landing_page_check()`` to attach the result.
    """

    url: str
    reachable: bool
    """``True`` if the URL returned HTTP 200."""

    load_time_seconds: float | None
    """Elapsed time for the full response, or ``None`` if unreachable."""

    language_detected: str | None
    """ISO 639-1 language code detected in ``<html lang="…">``, or ``None``."""

    https: bool
    """``True`` if the URL scheme is ``https``."""

    error_message: str | None = None
    """Human-readable error when ``reachable`` is ``False``."""

    page_title: str | None = None
    """Extracted ``<title>`` text — used for keyword relevance analysis."""

    h1_text: str | None = None
    """Text of the first ``<h1>`` element."""

    body_text_sample: str | None = None
    """First 2 000 characters of visible body text."""


@dataclass
class ValidationContext:
    """External data provided to the validator by the caller.

    All attributes default to safe values so tests can pass only what
    they need.

    Attributes
    ----------
    landing_page_results
        Mapping of ``final_url`` → ``LandingPageCheckResult``.  When a URL
        is absent the rule skips the check (emits a warning, not a failure),
        so legacy tests that don't care about Rule 6 still pass.
    has_conversion_tracking
        ``True`` when the linked Google Ads account has at least one *active*
        (ENABLED + include_in_conversions_metric) conversion action.
        Defaults to ``True`` so Rule 7 is permissive unless explicitly set.
    protected_brands
        Extra brand/trademark terms to block in addition to the built-in
        list.  Typical source: Adept customer domain registry.
    """

    landing_page_results: dict[str, LandingPageCheckResult] = field(default_factory=dict)
    has_conversion_tracking: bool = True
    protected_brands: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Rule 1 — Budget consistency
# ---------------------------------------------------------------------------

_BUDGET_TOLERANCE: float = 0.05  # ± 5 %


def _rule_budget(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 1: daily_budget_micros == monthly_budget_pln / 30 ± 5 %."""
    errors: list[str] = []
    expected = int(brief.monthly_budget_pln / Decimal("30") * Decimal("1_000_000"))
    if expected == 0:
        errors.append("Rule 1 (Budget): monthly_budget_pln is zero — cannot validate budget")
        return errors

    actual = proposal.daily_budget_micros
    drift = abs(actual - expected) / expected
    if drift > _BUDGET_TOLERANCE:
        errors.append(
            f"Rule 1 (Budget): daily_budget_micros {actual:,} deviates "
            f"{drift:.1%} from expected {expected:,} "
            f"(monthly {brief.monthly_budget_pln} PLN / 30 * 1 000 000). "
            f"Allowed tolerance: ±{_BUDGET_TOLERANCE:.0%}."
        )
    return errors


# ---------------------------------------------------------------------------
# Rule 2 — Protected keywords
# ---------------------------------------------------------------------------

# Adept standard protected list — competitor brands, common trademark terms,
# and categories that are legally or ethically restricted.
_BUILT_IN_PROTECTED: frozenset[str] = frozenset(
    {
        # Major global ad platforms / Adept-category competitors
        "google ads",
        "google adwords",
        "facebook ads",
        "meta ads",
        "bing ads",
        "microsoft ads",
        "adwords",
        # Adept own brand
        "adept",
        "adcopilot",
        # Trademark-sensitive generic terms that often cause policy issues
        "trademarked",
        "registered trademark",
        "®",
        "™",
    }
)

_PROTECTED_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(_BUILT_IN_PROTECTED)) + r")\b",
    re.IGNORECASE,
)


def _rule_protected_keywords(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 2: No keyword may match a protected brand or trademark term."""
    errors: list[str] = []

    # Merge built-in list with caller-supplied extras
    extra_patterns: list[re.Pattern[str]] = []
    for brand in ctx.protected_brands:
        try:  # noqa: SIM105
            extra_patterns.append(
                re.compile(r"\b" + re.escape(brand.lower()) + r"\b", re.IGNORECASE)
            )
        except re.error:
            pass

    def _is_protected(text: str) -> str | None:
        """Return the matched term if *text* contains a protected keyword."""
        m = _PROTECTED_PATTERN.search(text)
        if m:
            return m.group(0)
        for pat in extra_patterns:
            m2 = pat.search(text)
            if m2:
                return m2.group(0)
        return None

    for ag in proposal.ad_groups:
        for kw in ag.keywords:
            hit = _is_protected(kw.text)
            if hit:
                errors.append(
                    f"Rule 2 (Protected KW): keyword '{kw.text}' in ad group "
                    f"'{ag.name}' matches protected term '{hit}'. "
                    "Remove or replace this keyword."
                )
    return errors


# ---------------------------------------------------------------------------
# Rule 3 — Keyword count per ad group
# ---------------------------------------------------------------------------

_MIN_KW: int = 3
_MAX_KW: int = 15


def _rule_keyword_count(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 3: every ad group must have 3–15 keywords (inclusive)."""
    errors: list[str] = []
    if not proposal.ad_groups:
        errors.append("Rule 3 (KW Count): proposal has no ad groups.")
        return errors

    for ag in proposal.ad_groups:
        count = len(ag.keywords)
        if count < _MIN_KW:
            errors.append(
                f"Rule 3 (KW Count): ad group '{ag.name}' has {count} keyword(s) "
                f"— minimum is {_MIN_KW}. Add more relevant keywords."
            )
        elif count > _MAX_KW:
            errors.append(
                f"Rule 3 (KW Count): ad group '{ag.name}' has {count} keywords "
                f"— maximum is {_MAX_KW}. Split into multiple ad groups or remove excess."
            )
    return errors


# ---------------------------------------------------------------------------
# Rule 4 — Negatives completeness
# ---------------------------------------------------------------------------

# Standard Adept negative list that every campaign must contain at least one
# term from each category (checked as substring matches, case-insensitive).
# Structured as (category_label, list_of_acceptable_terms).
_STANDARD_NEGATIVE_CATEGORIES: list[tuple[str, list[str]]] = POLISH_STANDARD_NEGATIVES

# Vertical-specific standard negatives (at least one term per vertical block
# must appear in the proposal's negative keyword list).
_VERTICAL_NEGATIVES: dict[str, list[str]] = {
    # English detection keys → Polish term lists
    "salon": VERTICAL_NEGATIVES_PL["salon"],
    "ecommerce": VERTICAL_NEGATIVES_PL["ecommerce"],
    "restaurant": VERTICAL_NEGATIVES_PL["restauracja"],
    "legal": VERTICAL_NEGATIVES_PL["prawnik"],
    "medical": VERTICAL_NEGATIVES_PL["lekarz"],
    # Polish vertical keys
    "restauracja": VERTICAL_NEGATIVES_PL["restauracja"],
    "prawnik": VERTICAL_NEGATIVES_PL["prawnik"],
    "lekarz": VERTICAL_NEGATIVES_PL["lekarz"],
    "nieruchomości": VERTICAL_NEGATIVES_PL["nieruchomości"],
    "edukacja": VERTICAL_NEGATIVES_PL["edukacja"],
    "usługi domowe": VERTICAL_NEGATIVES_PL["usługi domowe"],
}


def _detect_vertical_from_brief(brief: CampaignBrief) -> str | None:
    """Simple vertical detection from business description."""
    desc = brief.business_description.lower()
    _kw_map = {
        "salon": ["salon", "hair", "beauty", "spa", "nail", "makeup", "hairdress", "barber"],
        "ecommerce": ["shop", "store", "buy", "sell", "product", "ecommerce", "e-commerce"],
        "restaurant": ["restaurant", "cafe", "food", "eat", "meal", "pizza", "diner"],
        "legal": ["lawyer", "legal", "attorney", "law firm", "solicitor"],
        "medical": ["doctor", "medical", "clinic", "dentist", "health"],
    }
    best, best_score = None, 0
    for v, kws in _kw_map.items():
        score = sum(1 for kw in kws if kw in desc)
        if score > best_score:
            best, best_score = v, score
    return best if best_score > 0 else None


def _has_any_term(negatives_lower: list[str], terms: list[str]) -> bool:
    return any(
        any(t in neg for t in terms)
        for neg in negatives_lower
    )


def _rule_negatives(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 4: negatives must cover standard categories + vertical + user exclusions."""
    errors: list[str] = []
    neg_lower = [n.lower() for n in proposal.negative_keywords]

    # 4a — standard categories
    for category, terms in _STANDARD_NEGATIVE_CATEGORIES:
        if not _has_any_term(neg_lower, terms):
            errors.append(
                f"Rule 4 (Negatives): missing standard negative category "
                f"'{category}'. Add at least one of: {terms[:3]}…"
            )

    # 4b — vertical-specific
    vertical = _detect_vertical_from_brief(brief)
    if vertical and vertical in _VERTICAL_NEGATIVES:
        v_terms = _VERTICAL_NEGATIVES[vertical]
        if not _has_any_term(neg_lower, v_terms):
            errors.append(
                f"Rule 4 (Negatives): missing vertical-specific negative for "
                f"'{vertical}'. Add at least one of: {v_terms[:3]}…"
            )

    # 4c — user-specified exclusions
    missing_exclusions = [
        excl for excl in brief.exclusions
        if excl.strip() and not _has_any_term(neg_lower, [excl.lower()])
    ]
    for excl in missing_exclusions:
        errors.append(
            f"Rule 4 (Negatives): user-specified exclusion '{excl}' is missing "
            "from proposal negative keywords. Add it verbatim."
        )

    return errors


# ---------------------------------------------------------------------------
# Rule 5 — Ad copy character limits
# ---------------------------------------------------------------------------

_MAX_HEADLINE_CHARS: int = 30
_MAX_DESC_CHARS: int = 90
_MAX_PATH_CHARS: int = 15
_MIN_HEADLINES: int = 3
_MIN_DESCS: int = 2


def _rule_ad_copy(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 5: each ad has ≥3 headlines ≤30 chars and ≥2 descriptions ≤90 chars."""
    errors: list[str] = []

    for ag in proposal.ad_groups:
        if not ag.ads:
            errors.append(
                f"Rule 5 (Ad Copy): ad group '{ag.name}' has no ads. "
                "Add at least one RSA."
            )
            continue

        for ad_idx, ad in enumerate(ag.ads):
            prefix = f"Rule 5 (Ad Copy): ad[{ad_idx}] in '{ag.name}'"

            # Headline count
            if len(ad.headlines) < _MIN_HEADLINES:
                errors.append(
                    f"{prefix}: only {len(ad.headlines)} headline(s) — "
                    f"minimum {_MIN_HEADLINES} required."
                )
            # Headline length
            for i, hl in enumerate(ad.headlines):
                if len(hl) > _MAX_HEADLINE_CHARS:
                    errors.append(
                        f"{prefix}: headline[{i}] is {len(hl)} chars "
                        f"(max {_MAX_HEADLINE_CHARS}): '{hl[:35]}…'"
                    )

            # Description count
            if len(ad.descriptions) < _MIN_DESCS:
                errors.append(
                    f"{prefix}: only {len(ad.descriptions)} description(s) — "
                    f"minimum {_MIN_DESCS} required."
                )
            # Description length
            for i, desc in enumerate(ad.descriptions):
                if len(desc) > _MAX_DESC_CHARS:
                    errors.append(
                        f"{prefix}: description[{i}] is {len(desc)} chars "
                        f"(max {_MAX_DESC_CHARS}): '{desc[:50]}…'"
                    )

            # Path segments
            for seg_idx, seg in enumerate(ad.path_segments):
                if len(seg) > _MAX_PATH_CHARS:
                    errors.append(
                        f"{prefix}: path_segment[{seg_idx}] is {len(seg)} chars "
                        f"(max {_MAX_PATH_CHARS}): '{seg}'"
                    )
    return errors


# ---------------------------------------------------------------------------
# Rule 6 — Landing page
# ---------------------------------------------------------------------------

_MAX_LOAD_SECONDS: float = 5.0


def _rule_landing_page(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 6: final_url must be HTTPS, return 200, load ≤5 s, match user language."""
    errors: list[str] = []

    # Collect unique final URLs
    urls: set[str] = set()
    for ag in proposal.ad_groups:
        for ad in ag.ads:
            if ad.final_url:
                urls.add(ad.final_url)

    if not urls:
        errors.append("Rule 6 (Landing Page): no final_url found in any ad.")
        return errors

    for url in sorted(urls):
        result = ctx.landing_page_results.get(url)

        if result is None:
            # Caller hasn't probed this URL yet — skip rather than fail hard,
            # but record an informational error so the caller knows.
            errors.append(
                f"Rule 6 (Landing Page): URL '{url}' was not probed — "
                "provide a LandingPageCheckResult in ValidationContext.landing_page_results."
            )
            continue

        if not result.https:
            errors.append(
                f"Rule 6 (Landing Page): URL '{url}' is not HTTPS. "
                "Google Ads requires secure landing pages."
            )

        if not result.reachable:
            msg = result.error_message or "unknown error"
            errors.append(
                f"Rule 6 (Landing Page): URL '{url}' is not reachable: {msg}"
            )
            continue  # skip timing / language checks if unreachable

        if result.load_time_seconds is not None and result.load_time_seconds > _MAX_LOAD_SECONDS:
            errors.append(
                f"Rule 6 (Landing Page): URL '{url}' loaded in "
                f"{result.load_time_seconds:.1f} s — must be under {_MAX_LOAD_SECONDS} s. "
                "Optimise page speed."
            )

        # Language check (case-insensitive, e.g. "en", "pl")
        if result.language_detected is not None: # noqa: SIM102
            if result.language_detected.lower() != brief.language.lower():
                errors.append(
                    f"Rule 6 (Landing Page): URL '{url}' appears to be in "
                    f"'{result.language_detected}' but the campaign language is "
                    f"'{brief.language}'. Ensure the landing page matches."
                )

    return errors


# ---------------------------------------------------------------------------
# Rule 6b — Landing page keyword relevance
# ---------------------------------------------------------------------------

_MIN_KEYWORD_OVERLAP = 0.30  # 30% of keyword tokens must appear in page content


def _tokenize(text: str) -> set[str]:
    """Lower-case word tokens, stripping punctuation."""
    return {w.lower() for w in re.findall(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", text) if len(w) > 2}


def _rule_landing_page_relevance(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 6b: top keyword tokens must appear in the landing page content.

    Only runs when the landing page check has page_title / body_text_sample populated.
    Fires as a warning (not blocker) when page content is unavailable.
    """
    errors: list[str] = []

    # Collect top-5 keywords by estimated CPC (highest CPC = highest intent)
    all_keywords: list[str] = []
    for ag in proposal.ad_groups:
        sorted_kws = sorted(ag.keywords, key=lambda k: k.estimated_cpc_micros, reverse=True)
        all_keywords.extend(kw.text for kw in sorted_kws[:5])
    top_keywords = all_keywords[:5]

    if not top_keywords:
        return errors

    kw_tokens: set[str] = set()
    for kw in top_keywords:
        kw_tokens |= _tokenize(kw)

    if not kw_tokens:
        return errors

    # Check each unique final URL
    urls: set[str] = set()
    for ag in proposal.ad_groups:
        for ad in ag.ads:
            if ad.final_url:
                urls.add(ad.final_url)

    for url in sorted(urls):
        result = ctx.landing_page_results.get(url)
        if result is None:
            continue  # already warned in _rule_landing_page

        # Build page content corpus
        page_parts = filter(None, [result.page_title, result.h1_text, result.body_text_sample])
        page_text = " ".join(page_parts)
        if not page_text:
            continue  # no content extracted — skip, don't fail

        page_tokens = _tokenize(page_text)
        matched = kw_tokens & page_tokens
        overlap = len(matched) / len(kw_tokens) if kw_tokens else 1.0

        if overlap < _MIN_KEYWORD_OVERLAP:
            missing = sorted(kw_tokens - page_tokens)[:5]
            errors.append(
                f"Rule 6b (Relevance): URL '{url}' does not mention key terms: "
                f"{', '.join(missing)}. "
                "Add these to your page title, headings, or body to improve Quality Score."
            )

    return errors


# ---------------------------------------------------------------------------
# Rule 7 — Bidding strategy
# ---------------------------------------------------------------------------

_MAXIMIZE_CLICKS = "MAXIMIZE_CLICKS"
_CONVERSION_STRATEGIES = frozenset(
    {
        "MAXIMIZE_CONVERSIONS",
        "TARGET_CPA",
        "TARGET_ROAS",
        "MAXIMIZE_CONVERSION_VALUE",
    }
)


def _rule_bidding(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 7: no conversion-based bidding when the account lacks conversion tracking."""
    errors: list[str] = []
    strategy = proposal.bidding_strategy.upper().replace(" ", "_")

    if not ctx.has_conversion_tracking and strategy in _CONVERSION_STRATEGIES:
        errors.append(
            f"Rule 7 (Bidding): strategy '{proposal.bidding_strategy}' requires "
            "conversion tracking, but the account has no active conversion actions. "
            f"Change to '{_MAXIMIZE_CLICKS}' or install conversion tracking first."
        )
    return errors


# ---------------------------------------------------------------------------
# Rule 8 — Geographic targeting
# ---------------------------------------------------------------------------

# Country names and ISO codes extracted from common formats:
#   "Warsaw, PL"  →  country = "PL"
#   "Poland"      →  country = "Poland"
#   "Kraków + 30 km"  → country = None (local targeting, allowed by default)

_COUNTRY_PATTERN = re.compile(
    r",\s*([A-Z]{2})\s*$"  # ", PL" at the end of the string
)

# Known country-level terms that imply global / multi-country targeting
_GLOBAL_TERMS: frozenset[str] = frozenset(
    {
        "worldwide",
        "global",
        "all countries",
        "international",
        "europe",
        "eu",
        "asia",
        "americas",
        "africa",
        "oceania",
    }
)

# Countries that are larger than or equal to a "country" — targeting at
# continent or "worldwide" level when the brief specifies a country is wrong.
def _extract_country(location: str) -> str | None:
    """Return the ISO-2 or plain country name from a location string."""
    m = _COUNTRY_PATTERN.search(location)
    if m:
        return m.group(1).upper()
    # Fall back to last token if it looks like a country word (≥4 chars, no digit)
    parts = [p.strip() for p in location.replace("+", ",").split(",")]
    last = parts[-1].strip()
    if len(last) >= 4 and not any(ch.isdigit() for ch in last):
        return last.title()
    return None


def _rule_geographic(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext,
) -> list[str]:
    """Rule 8: location_targeting must not be wider than the user's stated country."""
    errors: list[str] = []
    targeting = proposal.location_targeting.lower().strip()

    # Reject explicitly global / multi-continent terms
    for term in _GLOBAL_TERMS:
        if term in targeting:
            errors.append(
                f"Rule 8 (Geo): location_targeting '{proposal.location_targeting}' "
                f"contains global/regional term '{term}'. "
                "Targeting must be within the user's stated location: "
                f"'{brief.location}'."
            )
            return errors

    # If the brief specifies a country (e.g. "Warsaw, PL"), the proposal must
    # not target a *different* country.
    brief_country = _extract_country(brief.location)
    proposal_country = _extract_country(proposal.location_targeting)

    if brief_country and proposal_country:  # noqa: SIM102
        if brief_country.upper() != proposal_country.upper():
            errors.append(
                f"Rule 8 (Geo): location_targeting country '{proposal_country}' "
                f"does not match brief country '{brief_country}'. "
                "Targeting must stay within the user's stated country."
            )

    return errors


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_RULES = [
    ("budget", _rule_budget),
    ("protected_keywords", _rule_protected_keywords),
    ("keyword_count", _rule_keyword_count),
    ("negatives", _rule_negatives),
    ("ad_copy", _rule_ad_copy),
    ("landing_page", _rule_landing_page),
    ("landing_page_relevance", _rule_landing_page_relevance),
    ("bidding", _rule_bidding),
    ("geographic", _rule_geographic),
]


def validate_proposal(
    proposal: CampaignProposal,
    brief: CampaignBrief,
    ctx: ValidationContext | None = None,
) -> ValidationResult:
    """Run all 8 validation rules against *proposal* + *brief*.

    Parameters
    ----------
    proposal
        The ``CampaignProposal`` to validate.
    brief
        The originating ``CampaignBrief`` (supplies budget, language, exclusions).
    ctx
        Optional ``ValidationContext`` providing external data (landing-page
        probe results, conversion-tracking status, extra protected brands).
        When ``None`` a default context is used (permissive for rules 6, 7, 2).

    Returns
    -------
    ValidationResult
        ``passed=True`` only when *all* rules produce zero errors.
    """
    if ctx is None:
        ctx = ValidationContext()

    all_errors: list[str] = []
    rule_results: dict[str, list[str]] = {}

    for rule_name, rule_fn in _RULES:
        errs = rule_fn(proposal, brief, ctx)
        rule_results[rule_name] = errs
        all_errors.extend(errs)

    return ValidationResult(
        passed=len(all_errors) == 0,
        errors=all_errors,
        rule_results=rule_results,
    )
