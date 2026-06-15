"""Customer API keys — generation, hashing, verification (Phase 3 / T3.5).

Keys let Business customers read performance and recommendations
programmatically. Only a SHA-256 *hash* of each key is stored; the plaintext is
shown once at creation and never again. Each key carries a short non-secret
prefix so it can be displayed/identified in the UI without revealing the secret.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime

_KEY_PREFIX = "adw_live_"
_SECRET_BYTES = 24  # 32 chars base32-ish via token_urlsafe → ample entropy
_DISPLAY_PREFIX_LEN = 12  # how much of the plaintext to retain for display


@dataclass(frozen=True)
class GeneratedApiKey:
    """A freshly minted key — plaintext is returned to the caller exactly once."""

    plaintext: str
    key_hash: str
    display_prefix: str


@dataclass(frozen=True)
class ApiKey:
    """A stored API key (never holds the plaintext secret)."""

    id: str
    user_id: str
    name: str
    display_prefix: str
    key_hash: str
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


def hash_key(plaintext: str) -> str:
    """Return the hex SHA-256 of a key's plaintext (constant for a given key)."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_api_key() -> GeneratedApiKey:
    """Mint a new key: returns plaintext (show once), its hash, and a display prefix."""
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    plaintext = f"{_KEY_PREFIX}{secret}"
    return GeneratedApiKey(
        plaintext=plaintext,
        key_hash=hash_key(plaintext),
        display_prefix=plaintext[:_DISPLAY_PREFIX_LEN],
    )


def verify_key(plaintext: str, key_hash: str) -> bool:
    """Constant-time comparison of a presented key against a stored hash."""
    return secrets.compare_digest(hash_key(plaintext), key_hash)
