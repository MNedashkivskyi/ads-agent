"""Build a GTM container from a conversion plan (premium generator).

Replaces the static per-platform templates with a container generated from the
account's real conversion actions: one Google Ads Conversion Tracking (``awct``)
tag + one trigger per :class:`ConversionPlanItem`, each pointing at its own
conversion id/label and carrying the derived value.

Every GTM import rule we learned the hard way is enforced here:
- booleans are Parameter objects ``{"type": "BOOLEAN", "value": "true"}``;
- ``conversionId`` is the bare number (no ``AW-`` prefix);
- every ``awct`` tag has a non-empty ``conversionLabel``;
- every ``{{variable}}`` referenced is declared (built-in or user variable).
"""

from __future__ import annotations

from adcopilot.application.use_cases.build_conversion_plan import ConversionPlanItem
from adcopilot.domain.conversion_tracking.trigger_rules import TriggerKind

# Placeholder dropped into a PAGE_URL_CONTAINS trigger when we don't yet know the
# success URL. It deliberately matches no real page (so it never mis-fires) and
# is obvious for the user to replace in the guided step.
_REPLACE_HINT = "ZMIEN-NA-ADRES-STRONY-POTWIERDZENIA"

# Regex matching links to common downloadable files.
_FILE_DOWNLOAD_REGEX = r"\.(pdf|zip|docx?|xlsx?|pptx?|csv|mp3|mp4|dmg|exe|apk)(\?.*)?$"


def _numeric_conversion_id(conversion_id: str) -> str:
    return conversion_id[3:] if conversion_id.upper().startswith("AW-") else conversion_id


def _bool(value: bool) -> dict:
    return {"type": "BOOLEAN", "value": "true" if value else "false"}


def _build_tag(item: ConversionPlanItem, tag_id: str, trigger_id: str) -> dict:
    parameters: list[dict] = [
        {"type": "TEMPLATE", "key": "conversionId", "value": _numeric_conversion_id(item.conversion_id)},
        {"type": "TEMPLATE", "key": "conversionLabel", "value": item.conversion_label},
    ]
    if item.value is not None:
        parameters.append({"type": "TEMPLATE", "key": "conversionValue", "value": f"{item.value}"})
        if item.currency:
            parameters.append({"type": "TEMPLATE", "key": "currencyCode", "value": item.currency})
    parameters.append({"type": "BOOLEAN", "key": "enableRemarketing", "value": "false"})
    return {
        "accountId": "0",
        "containerId": "0",
        "tagId": tag_id,
        "name": f"GA Conversion — {item.name}",
        "type": "awct",
        "parameter": parameters,
        "firingTriggerId": [trigger_id],
    }


def _build_trigger(item: ConversionPlanItem, trigger_id: str) -> tuple[dict, dict[str, str]]:
    """Return (trigger, built-ins used as {type: name})."""
    base = {"accountId": "0", "containerId": "0", "triggerId": trigger_id, "name": item.name}

    if item.trigger_kind is TriggerKind.FORM_SUBMISSION:
        return (
            {
                **base,
                "type": "FORM_SUBMISSION",
                "waitForTags": _bool(True),
                "waitForTagsTimeout": {"type": "TEMPLATE", "value": "2000"},
                "checkValidation": _bool(True),
            },
            {},
        )

    if item.trigger_kind is TriggerKind.TEL_CLICK:
        return (
            {
                **base,
                "type": "LINK_CLICK",
                "waitForTags": _bool(False),
                "checkValidation": _bool(False),
                "filter": [
                    {
                        "type": "STARTS_WITH",
                        "parameter": [
                            {"type": "TEMPLATE", "key": "arg0", "value": "{{Click URL}}"},
                            {"type": "TEMPLATE", "key": "arg1", "value": "tel:"},
                        ],
                    }
                ],
            },
            {"CLICK_URL": "Click URL"},
        )

    if item.trigger_kind is TriggerKind.FILE_DOWNLOAD_CLICK:
        return (
            {
                **base,
                "type": "LINK_CLICK",
                "waitForTags": _bool(False),
                "checkValidation": _bool(False),
                "filter": [
                    {
                        "type": "MATCH_REGEX",
                        "parameter": [
                            {"type": "TEMPLATE", "key": "arg0", "value": "{{Click URL}}"},
                            {"type": "TEMPLATE", "key": "arg1", "value": _FILE_DOWNLOAD_REGEX},
                        ],
                    }
                ],
            },
            {"CLICK_URL": "Click URL"},
        )

    # PAGE_URL_CONTAINS (default for purchase / signup / page-view / unmapped).
    hint = item.trigger_hint or _REPLACE_HINT
    return (
        {
            **base,
            "type": "PAGEVIEW",
            "filter": [
                {
                    "type": "CONTAINS",
                    "parameter": [
                        {"type": "TEMPLATE", "key": "arg0", "value": "{{Page URL}}"},
                        {"type": "TEMPLATE", "key": "arg1", "value": hint},
                    ],
                }
            ],
        },
        {"PAGE_URL": "Page URL"},
    )


def build_gtm_container(
    items: list[ConversionPlanItem],
    container_name: str = "Adswise — Konwersje",
) -> dict:
    """Build a GTM container export dict from a (confirmed) conversion plan."""
    tags: list[dict] = []
    triggers: list[dict] = []
    builtins: dict[str, str] = {}

    for index, item in enumerate(items):
        trigger_id = str(2 * index + 1)
        tag_id = str(2 * index + 2)
        trigger, used = _build_trigger(item, trigger_id)
        triggers.append(trigger)
        builtins.update(used)
        tags.append(_build_tag(item, tag_id, trigger_id))

    container_version: dict = {
        "path": "accounts/0/containers/0/versions/0",
        "accountId": "0",
        "containerId": "0",
        "containerVersionId": "0",
        "name": container_name,
        "description": "Google Ads conversion tracking generated by Adswise",
        "container": {
            "path": "accounts/0/containers/0",
            "accountId": "0",
            "containerId": "0",
            "name": "Adswise Container",
            "domainName": [],
            "publicId": "GTM-XXXXXXX",
            "usageContext": ["WEB"],
        },
        "tag": tags,
        "trigger": triggers,
    }
    if builtins:
        container_version["builtInVariable"] = [
            {"accountId": "0", "containerId": "0", "type": var_type, "name": name}
            for var_type, name in builtins.items()
        ]

    return {
        "exportFormatVersion": 2,
        "exportTime": "2026-05-20",
        "containerVersion": container_version,
    }
