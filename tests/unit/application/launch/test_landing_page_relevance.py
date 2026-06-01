"""Unit tests for landing page relevance validation rule (Rule 6b)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from adcopilot.application.detection.validation import (
    LandingPageCheckResult,
    ValidationContext,
    validate_proposal,
)
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignProposal,
    KeywordProposal,
    LaunchStatus,
    MatchType,
)

# Non-placeholder host: bare example.com is skipped as a template placeholder
# (see _PLACEHOLDER_HOSTS), which would bypass the Rule 6b relevance check.
_URL = "https://kancelaria-example.pl/"
_NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _make_brief() -> CampaignBrief:
    return CampaignBrief(
        id="brief-1",
        user_id="user-1",
        account_id="acc-1",
        business_description="kancelaria prawna Warszawa",
        location="Warszawa",
        typical_customer_value=Decimal("500"),
        primary_action="phone call",
        monthly_budget_pln=Decimal("1000"),
        exclusions=[],
        language="pl",
        status=LaunchStatus.COLLECTING,
        created_at=_NOW,
    )


def _make_proposal(url: str, keywords: list[str]) -> CampaignProposal:
    kws = [
        KeywordProposal(text=k, match_type=MatchType.BROAD, estimated_cpc_micros=500_000)
        for k in keywords
    ]
    ad = AdProposal(
        headlines=["Kancelaria prawna"] * 3,
        descriptions=["Profesjonalna pomoc prawna"] * 2,
        path_segments=["prawnik"],
        final_url=url,
    )
    ag = AdGroupProposal(name="AG1", keywords=kws, ads=[ad])
    return CampaignProposal(
        id="prop-1",
        brief_id="brief-1",
        campaign_name="Test",
        ad_groups=[ag],
        negative_keywords=[],
        daily_budget_micros=33_000_000,
        location_targeting="PL",
        bidding_strategy="MAXIMIZE_CLICKS",
        sitelinks=[],
        callouts=[],
        structured_snippets=[],
        estimated_cpc_range=(100_000, 500_000),
        generated_at=_NOW,
    )


def _lp_result(url: str, body: str, title: str = "", h1: str = "") -> LandingPageCheckResult:
    return LandingPageCheckResult(
        url=url,
        reachable=True,
        https=True,
        load_time_seconds=0.5,
        language_detected="pl",
        page_title=title,
        h1_text=h1,
        body_text_sample=body,
    )


def _relevance_errors(result) -> list[str]:
    return [e for e in result.errors if "6b" in e]


def test_matching_keywords_pass():
    proposal = _make_proposal(_URL, ["kancelaria prawna", "prawnik Warszawa", "obsługa prawna"])
    brief = _make_brief()
    lp_ctx = ValidationContext(
        landing_page_results={
            _URL: _lp_result(
                _URL, "kancelaria prawna obsługa firm Warszawa prawnik", title="Kancelaria Prawna"
            )
        }
    )
    result = validate_proposal(proposal, brief, lp_ctx)
    assert not _relevance_errors(result), f"Unexpected 6b errors: {_relevance_errors(result)}"


def test_mismatching_keywords_fail():
    proposal = _make_proposal(_URL, ["kancelaria prawna", "prawnik Warszawa", "obsługa prawna"])
    brief = _make_brief()
    lp_ctx = ValidationContext(
        landing_page_results={
            _URL: _lp_result(_URL, "sklep internetowy obuwie buty sandały", title="Sklep z obuwiem")
        }
    )
    result = validate_proposal(proposal, brief, lp_ctx)
    assert len(_relevance_errors(result)) >= 1, "Expected at least one 6b error"


def test_unreachable_page_skips_relevance_check():
    proposal = _make_proposal(_URL, ["kancelaria prawna"])
    brief = _make_brief()
    unreachable = LandingPageCheckResult(
        url=_URL,
        reachable=False,
        https=True,
        load_time_seconds=5.1,
        language_detected=None,
        error_message="timeout",
    )
    lp_ctx = ValidationContext(landing_page_results={_URL: unreachable})
    result = validate_proposal(proposal, brief, lp_ctx)
    assert not _relevance_errors(result)


def test_no_lp_result_skips_relevance_check():
    proposal = _make_proposal(_URL, ["kancelaria prawna"])
    brief = _make_brief()
    lp_ctx = ValidationContext(landing_page_results={})
    result = validate_proposal(proposal, brief, lp_ctx)
    assert not _relevance_errors(result)
