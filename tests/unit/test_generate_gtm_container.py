"""Unit tests for GTM container generation substitution (conversion-id fix)."""

from __future__ import annotations

import json

import pytest

from adcopilot.application.use_cases.generate_gtm_container import generate_gtm_container


@pytest.mark.parametrize("platform", ["wordpress", "shopify", "woocommerce", "custom", "shoper"])
def test_real_values_leave_no_placeholders(platform: str) -> None:
    container = generate_gtm_container(
        conversion_id="AW-123456789",
        conversion_label="AbC-D_efGhIjk",
        platform=platform,
    )
    serialized = json.dumps(container)

    # A functional container must not ship the template placeholders…
    assert "{{CONVERSION_ID}}" not in serialized
    assert "{{CONVERSION_LABEL}}" not in serialized
    # …and must carry the real conversion identifiers.
    assert "AW-123456789" in serialized
    assert "AbC-D_efGhIjk" in serialized
