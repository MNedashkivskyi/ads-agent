"""Display-path derivation for the editable ad destination URL."""

from __future__ import annotations

from adcopilot.interfaces.api.proposal_editor import _derive_display_paths


def test_derives_two_segments_from_url() -> None:
    assert _derive_display_paths("https://mybodycare.pl/zabiegi/icoone") == ("zabiegi", "icoone")


def test_handles_url_without_scheme() -> None:
    assert _derive_display_paths("mybodycare.pl/oferta") == ("oferta", "")


def test_bare_domain_has_no_path() -> None:
    assert _derive_display_paths("mybodycare.pl") == ("", "")


def test_truncates_long_segments_to_15_chars() -> None:
    seg1, seg2 = _derive_display_paths("https://example.pl/bardzo-dluga-nazwa-strony/druga")
    assert len(seg1) <= 15 and seg1 == "bardzo-dluga-na"
    assert seg2 == "druga"


def test_ignores_extra_segments() -> None:
    assert _derive_display_paths("https://x.pl/a/b/c/d") == ("a", "b")
