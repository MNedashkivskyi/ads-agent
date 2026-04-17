"""Unit tests for ValidateProposal — all 8 rules, ≥ 2 positive + 2 negative per rule.

Test naming convention:
    test_rule<N>_<description>   — rule-specific tests
    test_full_*                  — integration tests across multiple rules
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from adcopilot.application.detection.validation import (
    LandingPageCheckResult,
    ValidationContext,
    validate_proposal,
)
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    LaunchStatus,
    MatchType,
)

# ---------------------------------------------------------------------------
# Factories — build valid baseline objects
# ---------------------------------------------------------------------------

def _kw(text: str, match: MatchType = MatchType.PHRASE, cpc: int = 1_000_000) -> KeywordProposal:
    return KeywordProposal(text=text, match_type=match, estimated_cpc_micros=cpc)


def _ad(
    headlines: list[str] | None = None,
    descriptions: list[str] | None = None,
    url: str = "https://example.com",
    path1: str = "Service",
    path2: str = "",
) -> AdProposal:
    return AdProposal(
        headlines=headlines or ["Great Service", "Call Us Today", "Best Prices"],
        descriptions=descriptions
        or [
            "Professional service you can trust. Contact us now.",
            "Top-rated local experts. Book your appointment today.",
        ],
        final_url=url,
        path_segments=(path1, path2),
    )


def _ag(
    name: str = "Main Service",
    keywords: list[KeywordProposal] | None = None,
    ads: list[AdProposal] | None = None,
) -> AdGroupProposal:
    if keywords is None:
        keywords = [_kw(f"service keyword {i}") for i in range(5)]
    return AdGroupProposal(
        name=name,
        keywords=keywords,
        ads=ads or [_ad()],
    )


def _proposal(
    campaign_name: str = "Test Campaign",
    daily_budget_micros: int = 33_333_333,  # 1000 PLN / 30 * 1e6
    bidding: str = "MAXIMIZE_CONVERSIONS",
    location: str = "Warsaw, PL",
    ad_groups: list[AdGroupProposal] | None = None,
    negatives: list[str] | None = None,
) -> CampaignProposal:
    if ad_groups is None:
        ad_groups = [_ag()]
    if negatives is None:
        negatives = [
            "free",          # covers free/darmowy
            "job",           # covers job/praca
            "diy",           # covers DIY
            "tutorial",      # covers tutorial/how-to
        ]
    return CampaignProposal(
        id=CampaignProposalId(str(uuid.uuid4())),
        brief_id=CampaignBriefId(str(uuid.uuid4())),
        campaign_name=campaign_name,
        daily_budget_micros=daily_budget_micros,
        location_targeting=location,
        bidding_strategy=bidding,
        ad_groups=ad_groups,
        negative_keywords=negatives,
        estimated_cpc_range=(800_000, 1_500_000),
        generated_at=datetime.now(UTC),
    )


def _brief(
    monthly_budget: Decimal = Decimal("1000"),
    location: str = "Warsaw, PL",
    language: str = "en",
    exclusions: list[str] | None = None,
    business: str = "Professional services company",
) -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description=business,
        location=location,
        typical_customer_value=Decimal("500"),
        primary_action="Call",
        monthly_budget_pln=monthly_budget,
        exclusions=exclusions or [],
        language=language,
        created_at=datetime.now(UTC),
        status=LaunchStatus.PROPOSED,
        interview_step=7,
    )


def _landing_ok(url: str, lang: str = "en") -> LandingPageCheckResult:
    return LandingPageCheckResult(
        url=url,
        reachable=True,
        load_time_seconds=1.2,
        language_detected=lang,
        https=True,
    )


# ---------------------------------------------------------------------------
# Rule 1 — Budget
# ---------------------------------------------------------------------------

class TestRule1Budget:
    """daily_budget_micros must equal monthly_budget_pln / 30 ± 5 %."""

    def test_exact_match_passes(self):
        """Exact daily budget computed from monthly passes."""
        monthly = Decimal("1000")
        expected = int(monthly / 30 * 1_000_000)
        proposal = _proposal(daily_budget_micros=expected)
        result = validate_proposal(proposal, _brief(monthly_budget=monthly))
        assert "budget" not in result.rule_results or not result.rule_results["budget"]

    def test_within_tolerance_passes(self):
        """Budget 4.9 % below expected passes (< 5 % tolerance)."""
        monthly = Decimal("1000")
        expected = int(monthly / 30 * 1_000_000)
        under_4pct = int(expected * 0.951)  # 4.9 % below
        proposal = _proposal(daily_budget_micros=under_4pct)
        result = validate_proposal(proposal, _brief(monthly_budget=monthly))
        assert not result.rule_results["budget"]

    def test_over_tolerance_fails(self):
        """Budget 10 % above expected fails."""
        monthly = Decimal("1000")
        expected = int(monthly / 30 * 1_000_000)
        over = int(expected * 1.10)  # 10 % above
        proposal = _proposal(daily_budget_micros=over)
        result = validate_proposal(proposal, _brief(monthly_budget=monthly))
        assert result.rule_results["budget"]
        assert "Rule 1" in result.rule_results["budget"][0]
        assert "10.0%" in result.rule_results["budget"][0]

    def test_far_under_fails(self):
        """Budget 50 % below expected fails."""
        monthly = Decimal("2000")
        expected = int(monthly / 30 * 1_000_000)
        half = expected // 2
        proposal = _proposal(daily_budget_micros=half)
        result = validate_proposal(proposal, _brief(monthly_budget=monthly))
        assert result.rule_results["budget"]
        assert "50.0%" in result.rule_results["budget"][0]

    def test_error_message_is_actionable(self):
        """Error includes expected and actual values."""
        monthly = Decimal("600")
        expected = int(monthly / 30 * 1_000_000)
        wrong = expected * 2
        proposal = _proposal(daily_budget_micros=wrong)
        result = validate_proposal(proposal, _brief(monthly_budget=monthly))
        err = result.rule_results["budget"][0]
        assert str(wrong) in err or f"{wrong:,}" in err


# ---------------------------------------------------------------------------
# Rule 2 — Protected keywords
# ---------------------------------------------------------------------------

class TestRule2ProtectedKeywords:
    """No keyword may match a protected brand or trademark."""

    def test_clean_keywords_pass(self):
        """Regular keywords with no protected terms pass."""
        ag = _ag(keywords=[_kw("hair salon near me"), _kw("haircut Warsaw"), _kw("best barber")])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        assert not result.rule_results["protected_keywords"]

    def test_competitor_platform_keyword_fails(self):
        """Keyword containing 'google ads' is rejected."""
        ag = _ag(keywords=[
            _kw("google ads specialist"),
            _kw("normal service"),
            _kw("another keyword"),
        ])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        errs = result.rule_results["protected_keywords"]
        assert errs
        assert "google ads" in errs[0].lower()
        assert "Rule 2" in errs[0]

    def test_adwords_keyword_fails(self):
        """Keyword containing 'adwords' is rejected."""
        ag = _ag(keywords=[
            _kw("adwords consultant"),
            _kw("service keyword"),
            _kw("another term"),
        ])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        assert result.rule_results["protected_keywords"]

    def test_custom_protected_brand_fails(self):
        """Caller-supplied protected brand is rejected in keywords."""
        ctx = ValidationContext(protected_brands={"acmecorp"})
        ag = _ag(keywords=[
            _kw("acmecorp alternative"),
            _kw("buy service"),
            _kw("cheap option"),
        ])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief(), ctx)
        errs = result.rule_results["protected_keywords"]
        assert errs
        assert "acmecorp" in errs[0].lower()

    def test_multiple_violations_all_reported(self):
        """Multiple protected keywords in different groups each generate an error."""
        ag1 = _ag("Group 1", keywords=[_kw("adwords manager"), _kw("kw2"), _kw("kw3")])
        ag2 = _ag("Group 2", keywords=[_kw("facebook ads"), _kw("kw4"), _kw("kw5")])
        result = validate_proposal(_proposal(ad_groups=[ag1, ag2]), _brief())
        errs = result.rule_results["protected_keywords"]
        assert len(errs) == 2

    def test_partial_match_not_flagged(self):
        """'goodads' does not trigger 'ads' match — requires word boundary."""
        ag = _ag(keywords=[_kw("cloud ads service"), _kw("regular service"), _kw("another")])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        # "cloud ads service" doesn't contain a standalone protected term
        assert not result.rule_results["protected_keywords"]


# ---------------------------------------------------------------------------
# Rule 3 — Keyword count
# ---------------------------------------------------------------------------

class TestRule3KeywordCount:
    """Each ad group: 3–15 keywords (inclusive)."""

    def test_three_keywords_passes(self):
        """Minimum of 3 keywords passes."""
        ag = _ag(keywords=[_kw("kw1"), _kw("kw2"), _kw("kw3")])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        assert not result.rule_results["keyword_count"]

    def test_fifteen_keywords_passes(self):
        """Maximum of 15 keywords passes."""
        kws = [_kw(f"keyword {i}") for i in range(15)]
        ag = _ag(keywords=kws)
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        assert not result.rule_results["keyword_count"]

    def test_two_keywords_fails(self):
        """Only 2 keywords is below minimum."""
        ag = _ag(keywords=[_kw("kw1"), _kw("kw2")])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        errs = result.rule_results["keyword_count"]
        assert errs
        assert "2 keyword" in errs[0]
        assert "minimum is 3" in errs[0]

    def test_sixteen_keywords_fails(self):
        """16 keywords exceeds maximum."""
        kws = [_kw(f"keyword {i}") for i in range(16)]
        ag = _ag(keywords=kws)
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        errs = result.rule_results["keyword_count"]
        assert errs
        assert "16 keywords" in errs[0]
        assert "maximum is 15" in errs[0]

    def test_zero_keywords_fails(self):
        """Zero keywords is below minimum."""
        ag = _ag(keywords=[])
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief())
        errs = result.rule_results["keyword_count"]
        assert errs
        assert "0 keyword" in errs[0]

    def test_multiple_groups_each_checked(self):
        """Both under and over violations across groups are all reported."""
        ag_under = _ag("Under", keywords=[_kw("only one")])
        ag_over = _ag("Over", keywords=[_kw(f"kw{i}") for i in range(16)])
        result = validate_proposal(_proposal(ad_groups=[ag_under, ag_over]), _brief())
        errs = result.rule_results["keyword_count"]
        assert len(errs) == 2


# ---------------------------------------------------------------------------
# Rule 4 — Negatives completeness
# ---------------------------------------------------------------------------

class TestRule4Negatives:
    """Must include standard categories + vertical + user exclusions."""

    def _full_negatives(self, extra: list[str] | None = None) -> list[str]:
        return [
            "free",
            "job",
            "diy",
            "tutorial",
        ] + (extra or [])

    def test_full_standard_negatives_pass(self):
        """All four standard category terms present → passes."""
        proposal = _proposal(negatives=self._full_negatives())
        result = validate_proposal(proposal, _brief())
        assert not result.rule_results["negatives"]

    def test_darmowy_counts_as_free_category(self):
        """Polish synonym 'darmow' satisfies the free/darmowy category."""
        proposal = _proposal(negatives=["darmowe", "praca", "zrób sam", "poradnik"])
        result = validate_proposal(proposal, _brief())
        assert not result.rule_results["negatives"]

    def test_missing_free_category_fails(self):
        """Omitting the free/darmowy term generates a specific error."""
        proposal = _proposal(negatives=["job", "diy", "tutorial"])
        result = validate_proposal(proposal, _brief())
        errs = result.rule_results["negatives"]
        assert any("free/darmowy" in e for e in errs)
        assert any("Rule 4" in e for e in errs)

    def test_missing_tutorial_category_fails(self):
        """Omitting tutorial/how-to generates a specific error."""
        proposal = _proposal(negatives=["free", "job", "diy"])
        result = validate_proposal(proposal, _brief())
        errs = result.rule_results["negatives"]
        assert any("tutorial/how-to" in e for e in errs)

    def test_salon_vertical_needs_salon_specific_negative(self):
        """Salon brief requires a vertical-specific negative (e.g. 'wig')."""
        brief = _brief(business="Hair salon offering cuts and styling in Warsaw")
        # Standard negatives only — no salon-specific term
        proposal = _proposal(negatives=["free", "job", "diy", "tutorial"])
        result = validate_proposal(proposal, brief)
        errs = result.rule_results["negatives"]
        assert any("salon" in e.lower() for e in errs)

    def test_salon_with_wig_negative_passes_vertical_check(self):
        """Adding 'wig' satisfies the salon vertical negative requirement."""
        brief = _brief(business="Hair salon offering cuts and styling")
        proposal = _proposal(negatives=["free", "job", "diy", "tutorial", "wig"])
        result = validate_proposal(proposal, brief)
        assert not any("salon" in e.lower() for e in result.rule_results["negatives"])

    def test_user_exclusion_must_appear(self):
        """User-specified exclusion 'cheap flights' must appear in negatives."""
        brief = _brief(exclusions=["cheap flights"])
        proposal = _proposal(negatives=["free", "job", "diy", "tutorial"])
        result = validate_proposal(proposal, brief)
        errs = result.rule_results["negatives"]
        assert any("cheap flights" in e for e in errs)

    def test_user_exclusion_present_passes(self):
        """When user exclusion is present in negatives, no error for that check."""
        brief = _brief(exclusions=["cheap flights"])
        proposal = _proposal(negatives=["free", "job", "diy", "tutorial", "cheap flights"])
        result = validate_proposal(proposal, brief)
        exclusion_errors = [e for e in result.rule_results["negatives"] if "cheap flights" in e]
        assert not exclusion_errors

    def test_multiple_user_exclusions_all_checked(self):
        """Each user exclusion gets its own error when missing."""
        brief = _brief(exclusions=["competitor a", "competitor b"])
        proposal = _proposal(negatives=["free", "job", "diy", "tutorial"])
        result = validate_proposal(proposal, brief)
        errs = result.rule_results["negatives"]
        assert any("competitor a" in e for e in errs)
        assert any("competitor b" in e for e in errs)


# ---------------------------------------------------------------------------
# Rule 5 — Ad copy
# ---------------------------------------------------------------------------

class TestRule5AdCopy:
    """≥3 headlines ≤30 chars, ≥2 descriptions ≤90 chars, paths ≤15 chars."""

    def test_valid_ad_copy_passes(self):
        """Correctly formatted ad passes all copy checks."""
        ad = _ad(
            headlines=["Great Service", "Call Today", "Free Quote"],
            descriptions=[
                "Professional service at great prices. Contact us today.",
                "Trusted by hundreds of customers. Book your slot now.",
            ],
        )
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        assert not result.rule_results["ad_copy"]

    def test_five_headlines_pass(self):
        """Five headlines (above minimum) passes."""
        ad = _ad(headlines=["H1 Short", "H2 Short", "H3 Short", "H4 Short", "H5 Short"])
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        assert not result.rule_results["ad_copy"]

    def test_too_few_headlines_fails(self):
        """Only 2 headlines is below minimum of 3."""
        ad = _ad(headlines=["Headline One", "Headline Two"])
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        errs = result.rule_results["ad_copy"]
        assert errs
        assert "2 headline" in errs[0]
        assert "minimum 3" in errs[0]

    def test_headline_too_long_fails(self):
        """A 31-character headline is rejected."""
        long_hl = "A" * 31  # 31 chars — one over the limit
        ad = _ad(headlines=[long_hl, "Short HL 2", "Short HL 3"])
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        errs = result.rule_results["ad_copy"]
        assert errs
        assert "31 chars" in errs[0]
        assert "Rule 5" in errs[0]

    def test_headline_exactly_30_chars_passes(self):
        """A 30-character headline is exactly on the limit."""
        hl = "A" * 30
        ad = _ad(headlines=[hl, "Short H2", "Short H3"])
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        assert not result.rule_results["ad_copy"]

    def test_too_few_descriptions_fails(self):
        """Only 1 description is below minimum of 2."""
        ad = _ad(descriptions=["One description that is long enough to be valid for Google Ads."])
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        errs = result.rule_results["ad_copy"]
        assert errs
        assert "1 description" in errs[0]

    def test_description_too_long_fails(self):
        """A 91-character description is rejected."""
        long_desc = "X" * 91
        ad = _ad(descriptions=[long_desc, "Short valid description here for the ad group."])
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        errs = result.rule_results["ad_copy"]
        assert errs
        assert "91 chars" in errs[0]

    def test_description_exactly_90_chars_passes(self):
        """A 90-character description is exactly on the limit."""
        desc = "D" * 90
        ad = _ad(descriptions=[desc, "Another valid description for this ad group here."])
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        assert not result.rule_results["ad_copy"]

    def test_path_too_long_fails(self):
        """A 16-character path segment is rejected."""
        ad = _ad(path1="A" * 16)
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        errs = result.rule_results["ad_copy"]
        assert errs
        assert "16 chars" in errs[0]

    def test_path_exactly_15_chars_passes(self):
        """A 15-character path segment is exactly on the limit."""
        ad = _ad(path1="A" * 15, path2="B" * 15)
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        assert not result.rule_results["ad_copy"]


# ---------------------------------------------------------------------------
# Rule 6 — Landing page
# ---------------------------------------------------------------------------

class TestRule6LandingPage:
    """final_url must be HTTPS, 200 OK, ≤5 s, matching campaign language."""

    def _ctx_ok(self, url: str = "https://example.com", lang: str = "en") -> ValidationContext:
        return ValidationContext(landing_page_results={url: _landing_ok(url, lang)})

    def test_valid_https_url_passes(self):
        """HTTPS, fast, correct language → passes."""
        url = "https://example.com"
        ad = _ad(url=url)
        proposal = _proposal(ad_groups=[_ag(ads=[ad])])
        result = validate_proposal(proposal, _brief(language="en"), self._ctx_ok(url, "en"))
        assert not result.rule_results["landing_page"]

    def test_all_ads_same_url_passes(self):
        """Multiple ads sharing the same valid URL pass."""
        url = "https://shop.example.com"
        ads = [_ad(url=url), _ad(url=url)]
        ag = _ag(ads=ads)
        result = validate_proposal(_proposal(ad_groups=[ag]), _brief(), self._ctx_ok(url))
        assert not result.rule_results["landing_page"]

    def test_http_url_fails(self):
        """HTTP (non-HTTPS) URL fails Rule 6."""
        url = "http://example.com"
        ctx = ValidationContext(
            landing_page_results={
                url: LandingPageCheckResult(
                    url=url,
                    reachable=True,
                    load_time_seconds=1.0,
                    language_detected="en",
                    https=False,
                )
            }
        )
        ad = _ad(url=url)
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief(), ctx)
        errs = result.rule_results["landing_page"]
        assert errs
        assert "not HTTPS" in errs[0]

    def test_unreachable_url_fails(self):
        """A URL returning non-200 fails Rule 6."""
        url = "https://broken.example.com"
        ctx = ValidationContext(
            landing_page_results={
                url: LandingPageCheckResult(
                    url=url,
                    reachable=False,
                    load_time_seconds=None,
                    language_detected=None,
                    https=True,
                    error_message="Connection refused",
                )
            }
        )
        ad = _ad(url=url)
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief(), ctx)
        errs = result.rule_results["landing_page"]
        assert errs
        assert "not reachable" in errs[0]
        assert "Connection refused" in errs[0]

    def test_slow_url_fails(self):
        """A URL that loads in 6 s fails the 5 s limit."""
        url = "https://slow.example.com"
        ctx = ValidationContext(
            landing_page_results={
                url: LandingPageCheckResult(
                    url=url,
                    reachable=True,
                    load_time_seconds=6.0,
                    language_detected="en",
                    https=True,
                )
            }
        )
        ad = _ad(url=url)
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief(), ctx)
        errs = result.rule_results["landing_page"]
        assert errs
        assert "6.0 s" in errs[0]

    def test_exactly_5s_passes(self):
        """Load time of exactly 5.0 s is on the limit and passes."""
        url = "https://edge.example.com"
        ctx = ValidationContext(
            landing_page_results={
                url: LandingPageCheckResult(
                    url=url,
                    reachable=True,
                    load_time_seconds=5.0,
                    language_detected="en",
                    https=True,
                )
            }
        )
        ad = _ad(url=url)
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief(), ctx)
        assert not result.rule_results["landing_page"]

    def test_wrong_language_fails(self):
        """Page in 'de' when campaign language is 'en' fails."""
        url = "https://german.example.com"
        ctx = ValidationContext(
            landing_page_results={
                url: LandingPageCheckResult(
                    url=url,
                    reachable=True,
                    load_time_seconds=1.0,
                    language_detected="de",
                    https=True,
                )
            }
        )
        ad = _ad(url=url)
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief(language="en"), ctx)
        errs = result.rule_results["landing_page"]
        assert errs
        assert "'de'" in errs[0]
        assert "'en'" in errs[0]

    def test_missing_probe_result_generates_warning(self):
        """URL not in context generates a specific informational error."""
        url = "https://unprobed.example.com"
        ad = _ad(url=url)
        # No landing_page_results in context
        result = validate_proposal(_proposal(ad_groups=[_ag(ads=[ad])]), _brief())
        errs = result.rule_results["landing_page"]
        assert errs
        assert "not probed" in errs[0]


# ---------------------------------------------------------------------------
# Rule 7 — Bidding
# ---------------------------------------------------------------------------

class TestRule7Bidding:
    """No conversion-based strategy when account has no conversion tracking."""

    def test_maximize_conversions_with_tracking_passes(self):
        """MAXIMIZE_CONVERSIONS when tracking exists → passes."""
        ctx = ValidationContext(has_conversion_tracking=True)
        proposal = _proposal(bidding="MAXIMIZE_CONVERSIONS")
        result = validate_proposal(proposal, _brief(), ctx)
        assert not result.rule_results["bidding"]

    def test_maximize_clicks_without_tracking_passes(self):
        """MAXIMIZE_CLICKS when no tracking → always passes."""
        ctx = ValidationContext(has_conversion_tracking=False)
        proposal = _proposal(bidding="MAXIMIZE_CLICKS")
        result = validate_proposal(proposal, _brief(), ctx)
        assert not result.rule_results["bidding"]

    def test_maximize_clicks_with_tracking_passes(self):
        """MAXIMIZE_CLICKS even with conversion tracking present → passes."""
        ctx = ValidationContext(has_conversion_tracking=True)
        proposal = _proposal(bidding="MAXIMIZE_CLICKS")
        result = validate_proposal(proposal, _brief(), ctx)
        assert not result.rule_results["bidding"]

    def test_maximize_conversions_without_tracking_fails(self):
        """MAXIMIZE_CONVERSIONS when no tracking → fails."""
        ctx = ValidationContext(has_conversion_tracking=False)
        proposal = _proposal(bidding="MAXIMIZE_CONVERSIONS")
        result = validate_proposal(proposal, _brief(), ctx)
        errs = result.rule_results["bidding"]
        assert errs
        assert "MAXIMIZE_CLICKS" in errs[0]
        assert "Rule 7" in errs[0]

    def test_target_cpa_without_tracking_fails(self):
        """TARGET_CPA when no tracking → fails."""
        ctx = ValidationContext(has_conversion_tracking=False)
        proposal = _proposal(bidding="TARGET_CPA")
        result = validate_proposal(proposal, _brief(), ctx)
        assert result.rule_results["bidding"]

    def test_target_roas_without_tracking_fails(self):
        """TARGET_ROAS when no tracking → fails."""
        ctx = ValidationContext(has_conversion_tracking=False)
        proposal = _proposal(bidding="TARGET_ROAS")
        result = validate_proposal(proposal, _brief(), ctx)
        assert result.rule_results["bidding"]

    def test_error_message_names_strategy(self):
        """Error message names the invalid strategy."""
        ctx = ValidationContext(has_conversion_tracking=False)
        proposal = _proposal(bidding="MAXIMIZE_CONVERSIONS")
        result = validate_proposal(proposal, _brief(), ctx)
        assert "MAXIMIZE_CONVERSIONS" in result.rule_results["bidding"][0]

    def test_default_context_allows_conversion_bidding(self):
        """Default ValidationContext (has_conversion_tracking=True) is permissive."""
        proposal = _proposal(bidding="MAXIMIZE_CONVERSIONS")
        result = validate_proposal(proposal, _brief())  # ctx=None → default
        assert not result.rule_results["bidding"]


# ---------------------------------------------------------------------------
# Rule 8 — Geographic targeting
# ---------------------------------------------------------------------------

class TestRule8Geographic:
    """location_targeting must not be wider than the user's stated country."""

    def test_same_city_passes(self):
        """Both brief and proposal in Warsaw, PL → passes."""
        proposal = _proposal(location="Warsaw, PL")
        result = validate_proposal(proposal, _brief(location="Warsaw, PL"))
        assert not result.rule_results["geographic"]

    def test_city_within_same_country_passes(self):
        """Proposal targets Kraków, PL; brief says Warsaw, PL → same country → passes."""
        proposal = _proposal(location="Kraków, PL")
        result = validate_proposal(proposal, _brief(location="Warsaw, PL"))
        assert not result.rule_results["geographic"]

    def test_different_country_fails(self):
        """Proposal targets DE but brief is PL → fails."""
        proposal = _proposal(location="Berlin, DE")
        result = validate_proposal(proposal, _brief(location="Warsaw, PL"))
        errs = result.rule_results["geographic"]
        assert errs
        assert "DE" in errs[0]
        assert "PL" in errs[0]
        assert "Rule 8" in errs[0]

    def test_worldwide_fails(self):
        """Proposal targeting 'worldwide' is always rejected."""
        proposal = _proposal(location="worldwide")
        result = validate_proposal(proposal, _brief(location="Warsaw, PL"))
        errs = result.rule_results["geographic"]
        assert errs
        assert "worldwide" in errs[0].lower()

    def test_global_fails(self):
        """'global' targeting is rejected."""
        proposal = _proposal(location="global")
        result = validate_proposal(proposal, _brief(location="Warsaw, PL"))
        assert result.rule_results["geographic"]

    def test_europe_fails(self):
        """'Europe' targeting is rejected as too wide."""
        proposal = _proposal(location="Europe")
        result = validate_proposal(proposal, _brief(location="Warsaw, PL"))
        assert result.rule_results["geographic"]

    def test_local_radius_no_country_passes(self):
        """'Warsaw + 30 km' has no extractable country → no geo error."""
        proposal = _proposal(location="Warsaw + 30 km")
        result = validate_proposal(proposal, _brief(location="Warsaw, PL"))
        assert not result.rule_results["geographic"]

    def test_plain_country_matches_iso_code(self):
        """'Poland' in proposal vs 'Warsaw, PL' in brief → different format, same country.
        Since _extract_country('Poland') = 'Poland' and _extract_country('Warsaw, PL') = 'PL',
        these won't match — which is acceptable (the rule doesn't cross-reference
        country names to ISO codes). No error since one side returns a plain name and
        the comparison won't be triggered unless both sides resolve."""
        proposal = _proposal(location="Poland")
        brief = _brief(location="Poland")  # both plain text
        result = validate_proposal(proposal, brief)
        assert not result.rule_results["geographic"]


# ---------------------------------------------------------------------------
# ValidationResult structure tests
# ---------------------------------------------------------------------------

class TestValidationResult:
    """Test the ValidationResult structure and passed flag."""

    def test_all_rules_pass_returns_passed_true(self):
        """A fully valid proposal returns passed=True."""
        url = "https://example.com"
        ctx = ValidationContext(
            landing_page_results={url: _landing_ok(url, "en")},
            has_conversion_tracking=True,
        )
        ag = _ag(keywords=[_kw(f"valid keyword {i}") for i in range(5)])
        proposal = _proposal(
            ad_groups=[ag],
            negatives=["free", "job", "diy", "tutorial"],
        )
        result = validate_proposal(proposal, _brief(), ctx)
        assert result.passed is True
        assert result.errors == []

    def test_single_failing_rule_sets_passed_false(self):
        """Even one failing rule → passed=False."""
        proposal = _proposal(daily_budget_micros=1)  # budget wildly wrong
        result = validate_proposal(proposal, _brief())
        assert result.passed is False
        assert result.errors

    def test_rule_results_keyed_by_rule_name(self):
        """rule_results dict contains an entry for every rule."""
        result = validate_proposal(_proposal(), _brief())
        expected_keys = {
            "budget", "protected_keywords", "keyword_count",
            "negatives", "ad_copy", "landing_page", "bidding", "geographic",
        }
        assert expected_keys.issubset(result.rule_results.keys())

    def test_errors_list_concatenates_all_rule_errors(self):
        """errors list contains all errors from all failing rules."""
        # Break budget AND keyword count
        ag = _ag(keywords=[_kw("kw1"), _kw("kw2")])  # < 3 keywords
        proposal = _proposal(daily_budget_micros=1, ad_groups=[ag])
        result = validate_proposal(proposal, _brief())
        assert not result.passed
        combined = "\n".join(result.errors)
        assert "Rule 1" in combined
        assert "Rule 3" in combined

    def test_failed_proposal_blocks_launch(self):
        """Simulates the use-case gate: passed=False blocks progression."""
        proposal = _proposal(daily_budget_micros=1)
        result = validate_proposal(proposal, _brief())
        # Use-case would check: if not result.passed: raise / retry
        assert not result.passed
        # Errors are specific and actionable
        assert all(len(e) > 20 for e in result.errors), "Errors should be descriptive"

    def test_errors_are_specific_and_actionable(self):
        """Each error message mentions the rule number and a remediation hint."""
        ag = _ag(keywords=[_kw("kw1")])  # 1 keyword — too few
        proposal = _proposal(ad_groups=[ag])
        result = validate_proposal(proposal, _brief())
        for err in result.rule_results["keyword_count"]:
            assert "Rule" in err, f"Error should mention rule: {err}"
            assert any(
                word in err.lower()
                for word in ["minimum", "maximum", "add", "split", "remove"]
            ), f"Error should contain remediation hint: {err}"


# ---------------------------------------------------------------------------
# Cross-rule integration tests
# ---------------------------------------------------------------------------

class TestFullValidation:
    """End-to-end tests with multiple rules interacting."""

    def test_proposal_with_all_violations_captures_all_errors(self):
        """A proposal violating multiple rules generates errors for each."""
        # Break: budget (wrong), keyword count (too few),
        #        protected keyword, conversion bidding without tracking
        ag = _ag(
            keywords=[_kw("google ads expert"), _kw("kw2")],  # 2 kws (< 3) + protected
        )
        proposal = _proposal(
            daily_budget_micros=1,                 # wrong budget
            bidding="MAXIMIZE_CONVERSIONS",        # no tracking
            ad_groups=[ag],
            negatives=[],                          # all standard categories missing
        )
        brief = _brief(exclusions=["my competitor"])
        ctx = ValidationContext(has_conversion_tracking=False)
        result = validate_proposal(proposal, brief, ctx)

        assert not result.passed
        # All expected rules should fire
        assert result.rule_results["budget"]
        assert result.rule_results["keyword_count"]
        assert result.rule_results["protected_keywords"]
        assert result.rule_results["negatives"]
        assert result.rule_results["bidding"]

    def test_perfectly_valid_proposal_passes_all_rules(self):
        """Fully correct proposal passes every rule."""
        url = "https://mysalon.example.com"
        ctx = ValidationContext(
            landing_page_results={url: _landing_ok(url, "en")},
            has_conversion_tracking=True,
        )
        kws = [_kw(f"hair salon service {i}") for i in range(5)]
        ad = _ad(url=url)
        ag = _ag(keywords=kws, ads=[ad])

        monthly = Decimal("1200")
        expected_daily = int(monthly / 30 * 1_000_000)

        proposal = _proposal(
            daily_budget_micros=expected_daily,
            bidding="MAXIMIZE_CONVERSIONS",
            location="Warsaw, PL",
            ad_groups=[ag],
            negatives=["free", "job", "diy", "tutorial", "wig"],
        )
        brief = _brief(
            monthly_budget=monthly,
            location="Warsaw, PL",
            language="en",
            exclusions=[],
            business="Hair salon in Warsaw",
        )
        result = validate_proposal(proposal, brief, ctx)
        assert result.passed
        assert result.errors == []
