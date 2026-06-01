"""Parse Google Ads conversion tag snippets.

The real conversion identifier and label for a GTM container live inside a
conversion action's ``tag_snippets[].event_snippet`` (gtag.js), e.g.::

    gtag('event', 'conversion', {'send_to': 'AW-123456789/AbC-D_efGhIjk'});

This module extracts the ``AW-<id>`` and ``<label>`` so the generated GTM
container points at the account's actual conversion action instead of a
placeholder.
"""

from __future__ import annotations

import re

# Matches the `AW-<digits>/<label>` token wherever it appears in a snippet,
# regardless of the surrounding quoting. Labels are URL-safe base64-ish strings.
_SEND_TO_RE = re.compile(r"AW-(\d+)/([A-Za-z0-9_-]+)")


def parse_conversion_send_to(event_snippet: str | None) -> tuple[str, str] | None:
    """Extract ``(conversion_id, conversion_label)`` from a gtag event snippet.

    ``conversion_id`` is returned with its ``AW-`` prefix (e.g. ``"AW-123456789"``).
    Returns ``None`` when the snippet is empty or contains no ``send_to`` target.
    """
    if not event_snippet:
        return None
    match = _SEND_TO_RE.search(event_snippet)
    if match is None:
        return None
    return (f"AW-{match.group(1)}", match.group(2))
