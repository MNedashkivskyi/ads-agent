"""Unit tests for :mod:`adcopilot.infrastructure.db.encryption`.

These tests do not touch the database.  The companion integration test
``tests/integration/db/test_repositories.py::
test_oauth_credentials_encrypted_at_rest`` asserts the same invariants
end-to-end against a real Postgres row — both live in the tree because
they catch different classes of regression (an ORM wiring bug would
slip past these unit tests but be caught by the integration test, and
vice versa).
"""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from adcopilot.infrastructure.db.encryption import decrypt, encrypt

_KEY = "test-encryption-key-32-bytes-ok!"
_OTHER_KEY = "different-key-also-32-bytes-!!!!"


def test_encrypt_roundtrips_cleanly() -> None:
    plaintext = "ya29.A0ARrdaM-sample-refresh-token-value"
    ciphertext = encrypt(plaintext, _KEY)
    assert decrypt(ciphertext, _KEY) == plaintext


def test_ciphertext_does_not_contain_plaintext() -> None:
    """Acceptance: no plaintext token visible in the encrypted blob."""
    plaintext = "1//0gXYZ-super-secret-refresh-token"
    ciphertext = encrypt(plaintext, _KEY)
    assert plaintext not in ciphertext


def test_ciphertext_has_fernet_v0_prefix() -> None:
    """Fernet v0 tokens always start with 'gAAAAA' (magic byte \\x80 b64)."""
    ciphertext = encrypt("anything", _KEY)
    assert ciphertext.startswith("gAAAAA"), (
        f"Expected Fernet-format ciphertext, got prefix {ciphertext[:8]!r}"
    )


def test_same_plaintext_encrypts_to_different_ciphertexts() -> None:
    """Fernet adds a random IV per encryption — equal plaintexts must differ."""
    plaintext = "ya29.repeated"
    c1 = encrypt(plaintext, _KEY)
    c2 = encrypt(plaintext, _KEY)
    assert c1 != c2
    # Both must still decrypt to the same thing.
    assert decrypt(c1, _KEY) == decrypt(c2, _KEY) == plaintext


def test_wrong_key_fails_to_decrypt() -> None:
    ciphertext = encrypt("secret", _KEY)
    with pytest.raises(InvalidToken):
        decrypt(ciphertext, _OTHER_KEY)


def test_tampered_ciphertext_fails_to_decrypt() -> None:
    """Flipping a single byte must invalidate the authentication tag."""
    ciphertext = encrypt("secret", _KEY)
    # Mutate a character from the middle of the token.
    idx = len(ciphertext) // 2
    tampered = ciphertext[:idx] + ("A" if ciphertext[idx] != "A" else "B") + ciphertext[idx + 1 :]
    with pytest.raises(InvalidToken):
        decrypt(tampered, _KEY)


def test_empty_string_roundtrips() -> None:
    """Defensive — no empty-string crashes.  The domain code normally
    rejects empty refresh_token upstream, but the primitive must still
    behave."""
    assert decrypt(encrypt("", _KEY), _KEY) == ""
