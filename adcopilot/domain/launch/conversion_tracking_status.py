"""Domain entity for conversion tracking detection results."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic import field_validator


class ConversionTrackingStatus(BaseModel):
    """Result of checking whether a Google Ads account has conversion tracking configured."""

    model_config = {"frozen": True}

    customer_id: str
    has_conversion_tracking: bool
    conversion_action_count: int = 0
    active_action_names: list[str] = Field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return self.has_conversion_tracking and self.conversion_action_count > 0
