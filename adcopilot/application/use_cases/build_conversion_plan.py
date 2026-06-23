"""Build a per-action conversion plan for the premium GTM generator.

Given the account's enabled conversion actions (with their real ``AW-`` ids and
Google Ads ``category``), the detected platform, the landing-page URLs and the
optional business economics, produce one :class:`ConversionPlanItem` per action:
a proposed trigger + a monetary value. The frontend renders this plan so the
user can confirm/edit the site-specific bits; the container builder turns the
confirmed plan into a GTM container.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.business_economics import BusinessEconomics
from adcopilot.domain.conversion_tracking.setup import ConversionActionTagInfo
from adcopilot.domain.conversion_tracking.trigger_rules import (
    TriggerKind,
    strategy_for_category,
)
from adcopilot.domain.value_derivation import derive_conversion_value


@dataclass(frozen=True)
class ConversionPlanItem:
    """A single conversion action mapped to a proposed GTM trigger + value."""

    conversion_action_id: int
    name: str
    category: str
    conversion_id: str  # AW-<id>
    conversion_label: str
    trigger_kind: TriggerKind
    needs_user_input: bool
    # PAGE_URL_CONTAINS only: the URL fragment to match. May be a placeholder the
    # user must replace when ``needs_user_input`` is True.
    trigger_hint: str
    value: float | None
    currency: str | None


def build_conversion_plan(
    actions: list[ConversionActionTagInfo],
    platform: str,
    final_urls: list[str] | None = None,
    economics: BusinessEconomics | None = None,
) -> list[ConversionPlanItem]:
    """Map each enabled conversion action to a proposed trigger and value."""
    urls = final_urls or []
    items: list[ConversionPlanItem] = []
    for action in actions:
        strategy = strategy_for_category(action.category, platform, urls)
        value = (
            derive_conversion_value(economics, category=action.category)
            if economics is not None
            else None
        )
        currency = economics.currency_code if (economics is not None and value is not None) else None
        items.append(
            ConversionPlanItem(
                conversion_action_id=action.conversion_action_id,
                name=action.name,
                category=action.category,
                conversion_id=action.conversion_id,
                conversion_label=action.conversion_label,
                trigger_kind=strategy.kind,
                needs_user_input=strategy.needs_user_input,
                trigger_hint=strategy.default_hint,
                value=value,
                currency=currency,
            )
        )
    return items
