"""Unit tests for campaign-name disambiguation and Google Ads error humanizing.

Covers the DUPLICATE_CAMPAIGN_NAME edge case (and related failure modes) that
caused launches to fail outright. The retry helper is exercised directly with a
mocked Google Ads CampaignService — no network or real client involved.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId
from adcopilot.infrastructure.google_ads.campaign_writer import (
    _MAX_CAMPAIGN_NAME_ATTEMPTS,
    CampaignWriter,
)
from adcopilot.infrastructure.google_ads.error_messages import (
    humanize_google_ads_error,
    is_duplicate_campaign_name,
)


class _DuplicateNameError(Exception):
    """Mimics a GoogleAdsException whose text embeds the duplicate-name enum."""

    def __str__(self) -> str:
        return (
            "GoogleAdsException ... errors { error_code { campaign_error: "
            'DUPLICATE_CAMPAIGN_NAME } message: "Trying to modify the name..." }'
        )


def _writer() -> CampaignWriter:
    return CampaignWriter(
        settings=MagicMock(spec=Settings),
        audit_log_repo=MagicMock(),
        account_id=AccountId("00000000-0000-0000-0000-000000000000"),
    )


def _ok_response(resource_name: str = "customers/1/campaigns/123") -> MagicMock:
    resp = MagicMock()
    resp.results = [SimpleNamespace(resource_name=resource_name)]
    return resp


# ---------------------------------------------------------------------------
# Retry-with-suffix behaviour
# ---------------------------------------------------------------------------


class TestUniqueName:
    def test_retries_with_suffix_then_succeeds(self) -> None:
        svc = MagicMock()
        svc.mutate_campaigns.side_effect = [_DuplicateNameError(), _ok_response()]
        campaign = SimpleNamespace(name="")

        rn = _writer()._mutate_campaign_with_unique_name(
            svc, "1", MagicMock(), campaign, "Salon Urody Warszawa"
        )

        assert rn == "customers/1/campaigns/123"
        # Second (successful) attempt used the disambiguated name.
        assert campaign.name == "Salon Urody Warszawa (2)"
        assert svc.mutate_campaigns.call_count == 2

    def test_first_attempt_uses_base_name(self) -> None:
        svc = MagicMock()
        svc.mutate_campaigns.side_effect = [_ok_response()]
        campaign = SimpleNamespace(name="")

        _writer()._mutate_campaign_with_unique_name(
            svc, "1", MagicMock(), campaign, "Moja Kampania"
        )

        assert campaign.name == "Moja Kampania"
        assert svc.mutate_campaigns.call_count == 1

    def test_gives_up_after_max_attempts(self) -> None:
        svc = MagicMock()
        svc.mutate_campaigns.side_effect = [_DuplicateNameError()] * (
            _MAX_CAMPAIGN_NAME_ATTEMPTS + 2
        )
        campaign = SimpleNamespace(name="")

        with pytest.raises(_DuplicateNameError):
            _writer()._mutate_campaign_with_unique_name(
                svc, "1", MagicMock(), campaign, "Taken Name"
            )
        assert svc.mutate_campaigns.call_count == _MAX_CAMPAIGN_NAME_ATTEMPTS

    def test_non_duplicate_error_is_not_retried(self) -> None:
        svc = MagicMock()
        svc.mutate_campaigns.side_effect = ValueError("INVALID_ARGUMENT: something else")
        campaign = SimpleNamespace(name="")

        with pytest.raises(ValueError):
            _writer()._mutate_campaign_with_unique_name(
                svc, "1", MagicMock(), campaign, "Some Name"
            )
        assert svc.mutate_campaigns.call_count == 1


# ---------------------------------------------------------------------------
# Error classification + humanizing
# ---------------------------------------------------------------------------


class TestHumanizer:
    def test_detects_duplicate_campaign_name(self) -> None:
        assert is_duplicate_campaign_name(_DuplicateNameError())
        assert not is_duplicate_campaign_name(ValueError("other"))

    @pytest.mark.parametrize(
        ("text", "needle"),
        [
            ("campaign_error: DUPLICATE_CAMPAIGN_NAME", "już istnieje"),
            ("invalid_grant: token has been expired or revoked", "Połącz konto Google Ads ponownie"),
            ("developer token not approved", "deweloperski"),
            ("USER_PERMISSION_DENIED", "uprawnień"),
            ("CUSTOMER_NOT_ENABLED account suspended", "aktywne"),
            ("MISSING_BILLING payments_profile", "płatności"),
            ("bidding_strategy requires conversion_tracking", "konwersji"),
            ("BudgetError amount too_low", "budżet"),
            ("RESOURCE_EXHAUSTED quota", "limit zapytań"),
            ("INTERNAL_ERROR unavailable", "nie odpowiada"),
        ],
    )
    def test_maps_known_codes_to_polish(self, text: str, needle: str) -> None:
        assert needle.lower() in humanize_google_ads_error(text).lower()

    def test_unknown_error_falls_back_to_generic(self) -> None:
        msg = humanize_google_ads_error("totally unrecognised failure xyz")
        assert "nieoczekiwany" in msg.lower()
        assert msg  # never empty
