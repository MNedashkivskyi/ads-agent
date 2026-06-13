"""Vertical — the locked taxonomy both learning loops key on.

Both learning loops (keyword-intent weights and creative-angle weights) aggregate
per ``vertical``. The taxonomy must be *stable and finite*: too granular and data
never accumulates; too coarse and weights blur across unlike businesses. This is
the one decision that constrains the whole spine, so it is locked here.

The canonical set is the taxonomy already produced by the campaign creator's
``detect_vertical_from_description`` (see ``adcopilot.domain.launch.templates``)
plus ``generic``. We additionally accept the per-YAML ``vertical_id`` slugs
(``beauty_salon``, ``dental_clinic``, ...) and Polish aliases as *aliases* that
normalise onto a canonical value, so whichever form the rest of the product
stored on an account/brief resolves cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from adcopilot.domain.exceptions import AdCopilotError


class InvalidVerticalError(AdCopilotError):
    """Raised when a vertical string is outside the locked taxonomy."""


class VerticalTaxonomy(StrEnum):
    """The locked, finite vertical taxonomy. Values match what the campaign
    creator stores on accounts/briefs."""

    SALON = "salon"
    ECOMMERCE = "ecommerce"
    RESTAURANT = "restaurant"
    LEGAL = "legal"
    MEDICAL = "medical"
    REAL_ESTATE = "nieruchomości"
    EDUCATION = "edukacja"
    HOME_SERVICES = "usługi domowe"
    GENERIC = "generic"


# Aliases that normalise onto a canonical taxonomy value. Keys are lower-cased.
# Covers the YAML ``vertical_id`` slugs and the Polish names used elsewhere.
_ALIASES: dict[str, VerticalTaxonomy] = {
    # YAML vertical_ids → canonical
    "beauty_salon": VerticalTaxonomy.SALON,
    "dental_clinic": VerticalTaxonomy.MEDICAL,
    "private_clinic": VerticalTaxonomy.MEDICAL,
    "physiotherapy": VerticalTaxonomy.MEDICAL,
    "law_firm": VerticalTaxonomy.LEGAL,
    "real_estate": VerticalTaxonomy.REAL_ESTATE,
    "tutoring": VerticalTaxonomy.EDUCATION,
    "cleaning_service": VerticalTaxonomy.HOME_SERVICES,
    "auto_repair": VerticalTaxonomy.HOME_SERVICES,
    "cafe": VerticalTaxonomy.RESTAURANT,
    "restaurant": VerticalTaxonomy.RESTAURANT,
    "fitness_studio": VerticalTaxonomy.MEDICAL,
    "personal_trainer": VerticalTaxonomy.MEDICAL,
    "photography": VerticalTaxonomy.GENERIC,
    # Polish/legacy aliases
    "restauracja": VerticalTaxonomy.RESTAURANT,
    "kawiarnia": VerticalTaxonomy.RESTAURANT,
    "prawnik": VerticalTaxonomy.LEGAL,
    "kancelaria": VerticalTaxonomy.LEGAL,
    "lekarz": VerticalTaxonomy.MEDICAL,
    "klinika": VerticalTaxonomy.MEDICAL,
    "nieruchomosci": VerticalTaxonomy.REAL_ESTATE,
}


@dataclass(frozen=True)
class Vertical:
    """A validated vertical, immutable and compared by value.

    Construct via :meth:`parse` (strict — raises on unknown) or
    :meth:`from_raw` (lenient — falls back to GENERIC for unknown values, used at
    ingest boundaries where stored data may predate the taxonomy).
    """

    value: VerticalTaxonomy

    @classmethod
    def parse(cls, raw: str) -> Vertical:
        """Normalise *raw* to a canonical vertical, raising on unknown values."""
        resolved = cls._resolve(raw)
        if resolved is None:
            raise InvalidVerticalError(
                f"Unknown vertical {raw!r}; not in taxonomy {[v.value for v in VerticalTaxonomy]}"
            )
        return cls(resolved)

    @classmethod
    def from_raw(cls, raw: str | None, *, default: VerticalTaxonomy = VerticalTaxonomy.GENERIC) -> Vertical:
        """Lenient parse — unknown/empty resolves to *default* (GENERIC)."""
        if not raw:
            return cls(default)
        resolved = cls._resolve(raw)
        return cls(resolved if resolved is not None else default)

    @staticmethod
    def _resolve(raw: str) -> VerticalTaxonomy | None:
        key = raw.strip().lower()
        for member in VerticalTaxonomy:
            if member.value == key:
                return member
        return _ALIASES.get(key)

    def __str__(self) -> str:
        return self.value.value
