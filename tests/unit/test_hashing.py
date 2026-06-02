from __future__ import annotations

from adcopilot.infrastructure.hashing import hash_email, hash_phone, normalize_phone

# Canonical SHA-256 of the normalized values (Google requires lowercase+trim for
# email, E.164 for phone, then SHA-256 hex).
EMAIL_HASH = "973dfe463ec85785f5f95af5ba3906eedb2d931c24e69824a89ea65dba4e813b"
PHONE_HASH = "3ad9f10d73829a714b1383221691d4dbf08484f3ceeae884f53053a1c7bb0a92"


def test_email_is_lowercased_and_trimmed_before_hashing() -> None:
    assert hash_email("test@example.com") == EMAIL_HASH
    assert hash_email("  Test@Example.COM  ") == EMAIL_HASH


def test_invalid_email_returns_none() -> None:
    assert hash_email("notanemail") is None
    assert hash_email("") is None
    assert hash_email("   ") is None


def test_phone_normalized_to_e164_before_hashing() -> None:
    assert hash_phone("+16502530000") == PHONE_HASH
    # Formatting characters are stripped; result matches the clean E.164 form.
    assert hash_phone("+1 (650) 253-0000") == PHONE_HASH
    assert normalize_phone("+1 (650) 253-0000") == "+16502530000"


def test_phone_without_country_code_returns_none() -> None:
    # Without a leading '+' we cannot trust the country code, so refuse to hash.
    assert hash_phone("6502530000") is None
    assert hash_phone("") is None
