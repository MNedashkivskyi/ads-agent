"""Value objects for bootstrapping conversion tracking.

These types describe the result of *creating* a conversion action (and reading
back its tag snippets) so that callers — the launch flow and the API — can hand
the user a ready-to-install tag instead of a placeholder. They live in the
domain layer so both the application use cases and the infrastructure adapter
depend on them, not on the Google Ads SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

# Macro categories we let users bootstrap. Aligned with the categories
# ``check_conversion_setup.has_macro_conversion_tracking`` treats as "real"
# conversions (PURCHASE, LEAD, SIGNUP, PHONE_CALL).
MACRO_CATEGORIES: frozenset[str] = frozenset(
    {"PURCHASE", "LEAD", "SIGNUP", "PHONE_CALL"}
)


class InvalidConversionCategory(ValueError):
    """Raised when a category outside :data:`MACRO_CATEGORIES` is requested."""


def validate_macro_category(category: str) -> str:
    """Normalise + validate a macro conversion category.

    Returns the upper-cased category; raises :class:`InvalidConversionCategory`
    when it is not one we support bootstrapping.
    """
    normalised = (category or "").strip().upper()
    if normalised not in MACRO_CATEGORIES:
        raise InvalidConversionCategory(
            f"{category!r} is not a supported macro category "
            f"(expected one of {sorted(MACRO_CATEGORIES)})"
        )
    return normalised


@dataclass(frozen=True)
class ConversionActionTag:
    """The installable tag for a conversion action.

    ``conversion_id`` keeps its ``AW-`` prefix (e.g. ``"AW-123456789"``);
    ``conversion_label`` is the per-action label. ``global_site_tag`` and
    ``event_snippet`` are the raw gtag.js snippets returned by Google Ads.
    """

    conversion_action_id: int
    conversion_id: str
    conversion_label: str
    global_site_tag: str
    event_snippet: str

    @property
    def send_to(self) -> str:
        """The ``AW-<id>/<label>`` token used in a gtag ``send_to``."""
        return f"{self.conversion_id}/{self.conversion_label}"


@dataclass(frozen=True)
class ConversionActionTagInfo:
    """One enabled conversion action plus its parsed conversion id/label.

    The premium GTM generator builds a tag + trigger per action, so it needs the
    action's ``name`` and ``category`` (to pick a trigger) alongside the real
    ``AW-<id>`` / ``<label>`` (to point the tag at the right conversion).
    """

    conversion_action_id: int
    name: str
    category: str
    conversion_id: str  # keeps the ``AW-`` prefix
    conversion_label: str
