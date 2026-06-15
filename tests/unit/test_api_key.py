"""Unit tests for customer API-key generation/verification (Phase 3 / T3.5)."""

from __future__ import annotations

from adcopilot.domain.api_key import generate_api_key, hash_key, verify_key


def test_generated_key_has_prefix_and_hash() -> None:
    g = generate_api_key()
    assert g.plaintext.startswith("adw_live_")
    assert g.display_prefix == g.plaintext[:12]
    assert g.key_hash == hash_key(g.plaintext)
    assert len(g.key_hash) == 64  # sha256 hex


def test_keys_are_unique() -> None:
    a = generate_api_key()
    b = generate_api_key()
    assert a.plaintext != b.plaintext
    assert a.key_hash != b.key_hash


def test_verify_matches_only_correct_key() -> None:
    g = generate_api_key()
    assert verify_key(g.plaintext, g.key_hash) is True
    assert verify_key("adw_live_wrong", g.key_hash) is False


def test_hash_is_stable() -> None:
    assert hash_key("adw_live_abc") == hash_key("adw_live_abc")
    assert hash_key("adw_live_abc") != hash_key("adw_live_abd")
