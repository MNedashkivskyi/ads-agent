"""Unit test: only the hook headline (position 1) is pinned in RSA creation.

Over-pinning (H1-H3) forces "Poor" Ad Strength and throttles impressions, so
the premium copy strategy pins ONLY the emotional hook to position 1 and leaves
the rest unpinned. This guards that behaviour without a real Google Ads client.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId
from adcopilot.domain.launch.entities import AdProposal
from adcopilot.infrastructure.google_ads.campaign_writer import CampaignWriter

_HEADLINE_1 = object()  # sentinel returned by ServedAssetFieldTypeEnum.HEADLINE_1


class _Asset:
    def __init__(self) -> None:
        self.text = ""
        self.pinned_field = None


class _RSA:
    def __init__(self) -> None:
        self.headlines: list[_Asset] = []
        self.descriptions: list[_Asset] = []
        self.path1 = ""
        self.path2 = ""


class _Ad:
    def __init__(self) -> None:
        self.final_urls: list[str] = []
        self.responsive_search_ad = _RSA()


class _AdGroupAd:
    def __init__(self) -> None:
        self.ad_group = ""
        self.status = None
        self.ad = _Ad()


class _Op:
    def __init__(self) -> None:
        self.create = _AdGroupAd()


def _fake_client() -> MagicMock:
    client = MagicMock()
    client.get_type.side_effect = lambda name: _Op() if name == "AdGroupAdOperation" else _Asset()
    client.enums.ServedAssetFieldTypeEnum.HEADLINE_1 = _HEADLINE_1
    client.enums.AdGroupAdStatusEnum.ENABLED = object()
    ad_service = MagicMock()
    ad_service.mutate_ad_group_ads.return_value = SimpleNamespace(
        results=[SimpleNamespace(resource_name="customers/1/adGroupAds/1~2")]
    )
    client.get_service.return_value = ad_service
    return client


@pytest.mark.asyncio
async def test_only_hook_headline_is_pinned() -> None:
    audit = MagicMock()
    audit.save = AsyncMock(return_value=None)
    writer = CampaignWriter(
        settings=MagicMock(spec=Settings),
        audit_log_repo=audit,
        account_id=AccountId("00000000-0000-0000-0000-000000000000"),
    )
    client = _fake_client()
    writer._build_client = MagicMock(return_value=client)  # type: ignore[method-assign]

    adp = AdProposal(
        headlines=[
            "Dieta nie dziala na cellulit",  # the hook
            "Nowoczesna technologia EMS",
            "Umow wizyte",
            "Sprawdz oferte",
        ],
        descriptions=["Zobacz, co naprawde dziala. Umow wizyte juz dzis.", "Profesjonalna obsluga."],
        final_url="https://example.com",
        path_segments=("warszawa", ""),
    )

    await writer.create_ads("123", "refresh", "customers/1/adGroups/1", [adp])

    ops = client.get_service.return_value.mutate_ad_group_ads.call_args.kwargs["operations"]
    assert len(ops) == 1
    headlines = ops[0].create.ad.responsive_search_ad.headlines
    assert len(headlines) == 4
    # Only the first (hook) headline is pinned to position 1.
    assert headlines[0].pinned_field is _HEADLINE_1
    assert all(h.pinned_field is None for h in headlines[1:])
