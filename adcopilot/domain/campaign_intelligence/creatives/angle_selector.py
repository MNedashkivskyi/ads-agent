"""angle_selector — slot allocation across angles, delegating to the shared spine.

Thin wrapper so the creative track uses the *same* explore/exploit machinery as
the keyword track. Cold start → uniform; learned winners → up-weighted; floor
keeps every angle alive.
"""

from __future__ import annotations

from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.shared import dimension_selector
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)

_ANGLE_VALUES = [a.value for a in Angle]


def allocate(
    total_slots: int,
    performance: dict[str, DimensionPerformance] | None = None,
    *,
    floor: int = 1,
) -> dict[str, int]:
    return dimension_selector.allocate(
        total_slots, _ANGLE_VALUES, performance or {}, floor=floor
    )
