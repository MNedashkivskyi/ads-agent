"""Use case: generate a ready-to-import GTM container JSON for a given account."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_TEMPLATES_DIR = (
    Path(__file__).parent.parent.parent / "domain" / "conversion_tracking" / "gtm_templates"
)

_ECOMMERCE_PLATFORMS = {"shopify", "woocommerce", "shoper"}
_LEAD_GEN_PLATFORMS = {"wordpress", "custom"}


def generate_gtm_container(
    conversion_id: str,
    conversion_label: str,
    platform: str,
) -> dict:
    """Return a GTM container export dict with conversion_id and label substituted."""
    template_path = _pick_template(platform)
    template = json.loads(template_path.read_text())
    container = copy.deepcopy(template)
    # GTM's Google Ads Conversion Tracking (awct) tag stores the Conversion ID as
    # a bare number and validates it as an integer — the "AW-" prefix lives only
    # in the gtag send_to. Strip it so GTM accepts the import.
    numeric_conversion_id = (
        conversion_id[3:] if conversion_id.upper().startswith("AW-") else conversion_id
    )
    _substitute(container, "{{CONVERSION_ID}}", numeric_conversion_id)
    _substitute(container, "{{CONVERSION_LABEL}}", conversion_label)
    logger.info(
        "gtm_container_generated",
        platform=platform,
        conversion_id=numeric_conversion_id,
        template=template_path.name,
    )
    return container


def _pick_template(platform: str) -> Path:
    if platform in _ECOMMERCE_PLATFORMS:
        return _TEMPLATES_DIR / "base_ecommerce.json"
    if platform in _LEAD_GEN_PLATFORMS:
        return _TEMPLATES_DIR / "base_lead_gen.json"
    return _TEMPLATES_DIR / "base_search.json"


def _substitute(obj: object, placeholder: str, value: str) -> None:
    """Recursively replace placeholder strings inside the container dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and placeholder in v:
                obj[k] = v.replace(placeholder, value)
            else:
                _substitute(v, placeholder, value)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and placeholder in item:
                obj[i] = item.replace(placeholder, value)
            else:
                _substitute(item, placeholder, value)
