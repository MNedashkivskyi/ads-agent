"""Angle — the strategic dimension of the creative track.

A hook anchored on the customer's *state* converts; one anchored on the product
is gray. The angle is which facet of that state the hook leans on (the pain, the
failed alternative, the result they want, ...). Like keyword intent-types, angles
are the dimension the learning spine attributes performance to.
"""

from __future__ import annotations

from enum import StrEnum

ANGLE_DIMENSION = "angle"


class Angle(StrEnum):
    PAIN = "PAIN"  # name the pain ("Cellulit, który nie znika?")
    FAILED_ALTERNATIVE = "FAILED_ALTERNATIVE"  # "Diety i ćwiczenia nie pomogły?"
    RESULT = "RESULT"  # promise the outcome ("Gładsza skóra w 4 tygodnie")
    SOCIAL_PROOF = "SOCIAL_PROOF"  # "Zaufało nam 5000 klientek"
    OBJECTION = "OBJECTION"  # disarm the objection ("Bez bólu i rekonwalescencji")
    URGENCY = "URGENCY"  # scarcity/time ("Ostatnie wolne terminy w tym tygodniu")
    CURIOSITY = "CURIOSITY"  # open a loop ("Znasz prawdziwą przyczynę cellulitu?")

    @property
    def dimension_name(self) -> str:
        return ANGLE_DIMENSION
