"""Helpers for campaign targeting and final-URL normalization.

Pure functions (no I/O) used by the launch proposal-assembly and
campaign-creation paths. Keeping them here lets both the LLM-based and
template-based assemblers share identical behavior and lets the worker
resolve language constants without importing the Google Ads client.
"""

from __future__ import annotations

from urllib.parse import urlparse

__all__ = [
    "normalize_final_url",
    "language_constant_id",
    "dedupe_negatives",
]


def normalize_final_url(
    raw: str | None,
    fallback: str | None = "https://example.com",
) -> str | None:
    """Return a usable https final URL or ``fallback``.

    Accepts bare domains ("acme.pl") and adds an ``https://`` scheme.
    Validates that the host looks like a real domain (contains a dot).
    Returns ``fallback`` when the input is missing or unparseable.
    """
    if not raw or not raw.strip():
        return fallback

    candidate = raw.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parsed = urlparse(candidate)
    except (ValueError, TypeError):
        return fallback

    if parsed.scheme not in ("http", "https"):
        return fallback
    if not parsed.netloc or "." not in parsed.netloc:
        return fallback

    return candidate


# Google Ads language constant IDs.
# https://developers.google.com/google-ads/api/data/codes-formats#languages
_LANGUAGE_CONSTANTS: dict[str, str] = {
    "pl": "1031",
    "en": "1000",
    "de": "1001",
    "fr": "1002",
    "es": "1003",
    "it": "1004",
}


def language_constant_id(code: str | None) -> str:
    """Map an ISO 639-1 code to a Google Ads language constant ID.

    Defaults to Polish (1031) for unknown/missing codes — the primary market.
    """
    return _LANGUAGE_CONSTANTS.get((code or "pl").strip().lower(), "1031")


def dedupe_negatives(
    negatives: list[str],
    positive_texts: list[str],
) -> list[str]:
    """Drop negatives that collide with positive keywords, and de-duplicate.

    A negative keyword identical (case-insensitive, trimmed) to any positive
    keyword would suppress traffic we are explicitly bidding on, so it is
    removed. Order of first appearance is preserved.
    """
    positives_norm = {p.strip().casefold() for p in positive_texts if p and p.strip()}
    seen: set[str] = set()
    result: list[str] = []
    for neg in negatives:
        if not neg or not neg.strip():
            continue
        norm = neg.strip().casefold()
        if norm in positives_norm or norm in seen:
            continue
        seen.add(norm)
        result.append(neg)
    return result
