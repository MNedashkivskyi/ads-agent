"""Unit tests for parsing conversion tag snippets (GTM container fix)."""

from __future__ import annotations

import pytest

from adcopilot.domain.conversion_tracking.tag_parsing import parse_conversion_send_to

_EVENT_SNIPPET = """
<!-- Event snippet for Zakup conversion page -->
<script>
  gtag('event', 'conversion', {'send_to': 'AW-123456789/AbC-D_efGhIjk'});
</script>
"""


def test_parses_id_and_label_from_event_snippet() -> None:
    result = parse_conversion_send_to(_EVENT_SNIPPET)
    assert result == ("AW-123456789", "AbC-D_efGhIjk")


def test_parses_double_quoted_send_to() -> None:
    snippet = 'gtag("event", "conversion", {"send_to": "AW-987654321/Zz9_label"});'
    assert parse_conversion_send_to(snippet) == ("AW-987654321", "Zz9_label")


@pytest.mark.parametrize("value", ["", None, "no conversion target here", "AW-123"])
def test_returns_none_when_no_send_to(value: str | None) -> None:
    assert parse_conversion_send_to(value) is None


def test_returns_first_match_when_multiple_present() -> None:
    snippet = "AW-111/aaa then later AW-222/bbb"
    assert parse_conversion_send_to(snippet) == ("AW-111", "aaa")
