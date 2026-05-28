"""Domain entity for PageSpeed Insights analysis results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageSpeedResult(BaseModel):
    """Results from Google PageSpeed Insights API."""

    model_config = {"frozen": True}

    url: str
    performance_score: int | None = None  # 0–100; None if unavailable
    mobile_friendly: bool = False
    load_time_ms: int | None = None
    issues: list[str] = Field(default_factory=list)
    available: bool = True  # False when API is unreachable

    @property
    def score_label(self) -> str:
        if self.performance_score is None:
            return "unavailable"
        if self.performance_score >= 80:
            return "good"
        if self.performance_score >= 50:
            return "needs_improvement"
        return "poor"
