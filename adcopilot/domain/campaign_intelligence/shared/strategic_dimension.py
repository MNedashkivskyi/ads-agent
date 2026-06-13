"""StrategicDimension — the abstraction both tracks generate along.

Both the keyword problem and the hook problem have the same shape: generate
candidates along a *strategic dimension* that represents the customer's intent,
then learn which points on that dimension actually convert per vertical. The
keyword track's dimension is ``keyword_intent`` (BRAND / INTENT / PROBLEM); the
creative track's dimension is ``angle`` (pain, failed-alt, result, ...).

A concrete dimension value (e.g. ``KeywordIntent.PROBLEM``) is a *tagged
generation axis point*: it knows the name of the dimension it belongs to and its
own string value. The learning spine (``dimension_performance``,
``dimension_selector``) is written once against this protocol and reused by both
tracks — it never needs to know whether it is attributing keyword intents or
creative angles.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StrategicDimension(Protocol):
    """A single value on a tagged generation axis with a finite value set.

    Implementations are typically ``StrEnum`` members (see
    :class:`~adcopilot.domain.campaign_intelligence.keywords.value_objects.KeywordIntent`
    and :class:`~adcopilot.domain.campaign_intelligence.creatives.angle.Angle`).
    They expose:

    * ``value`` — the canonical string for this point (e.g. ``"PROBLEM"``),
      used as the storage key and the join key for performance attribution.
    * ``dimension_name`` — the stable name of the axis (e.g. ``"keyword_intent"``),
      used to namespace learned weights in ``dimension_performance``.
    """

    @property
    def value(self) -> str:
        """Canonical string value of this dimension point."""
        ...

    @property
    def dimension_name(self) -> str:
        """Stable name of the dimension this value belongs to."""
        ...


def dimension_values(member: type) -> tuple[str, ...]:
    """Return the finite set of string values for a dimension enum class.

    ``member`` must be a ``StrEnum`` (or any iterable enum whose members carry a
    ``.value``). Used by the selector and tests to enumerate the axis.
    """
    return tuple(m.value for m in member)  # type: ignore[attr-defined]
