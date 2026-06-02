"""First-party identifier hashing for Google Ads measurement uploads.

Google's Customer Match, Enhanced Conversions and Offline Conversion Import all
require user identifiers to be **normalized then SHA-256 hashed** (hex):

* email — trim whitespace, lowercase, then SHA-256
* phone — convert to E.164 (leading ``+`` and country code, digits only), then
  SHA-256

This is the single source of truth for that normalization so Customer Match and
the measurement upload paths can't drift apart.
"""

from __future__ import annotations

import hashlib
import re

_NON_DIGIT = re.compile(r"\D")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_email(email: str | None) -> str | None:
    """Return the SHA-256 hex of a normalized email, or None if it isn't valid."""
    if not email:
        return None
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return None
    return sha256_hex(normalized)


def normalize_phone(phone: str) -> str:
    """Best-effort E.164 normalization: keep a single leading '+' and the digits."""
    stripped = phone.strip()
    has_plus = stripped.startswith("+")
    digits = _NON_DIGIT.sub("", stripped)
    return ("+" if has_plus else "") + digits


def hash_phone(phone: str | None) -> str | None:
    """Return the SHA-256 hex of an E.164 phone, or None if it isn't usable.

    Requires a leading ``+`` (country code) — without it we cannot reliably
    determine the country, and an un-prefixed number would hash to a value
    Google can't match, so we refuse rather than upload bad data.
    """
    if not phone:
        return None
    normalized = normalize_phone(phone)
    if not normalized.startswith("+"):
        return None
    if len(_NON_DIGIT.sub("", normalized)) < 8:
        return None
    return sha256_hex(normalized)
