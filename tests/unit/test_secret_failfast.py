"""LAUNCH-005: refuse to start in production with insecure secret defaults."""

from __future__ import annotations

import pytest


def test_raises_in_production_with_default_secrets() -> None:
    from adcopilot.config import Settings

    s = Settings(ENV="production")  # defaults for SECRET_KEY / TOKEN_ENCRYPTION_KEY
    with pytest.raises(RuntimeError) as exc:
        s.assert_secure_for_production()
    assert "SECRET_KEY" in str(exc.value)
    assert "TOKEN_ENCRYPTION_KEY" in str(exc.value)


def test_passes_in_production_with_strong_secrets() -> None:
    from adcopilot.config import Settings

    s = Settings(
        ENV="production",
        SECRET_KEY="a-strong-random-secret-value-1234567890",
        TOKEN_ENCRYPTION_KEY="another-strong-random-32byte-key-xyz",
    )
    s.assert_secure_for_production()  # must not raise


def test_noop_in_dev_even_with_defaults() -> None:
    from adcopilot.config import Settings

    Settings(ENV="dev").assert_secure_for_production()  # must not raise
