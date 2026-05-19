"""LandingPageScore domain entity — PageSpeed + LLM audit result."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CoreWebVitals:
    lcp_ms: float | None = None           # Largest Contentful Paint
    fid_ms: float | None = None           # First Input Delay (deprecated but still reported)
    cls_score: float | None = None        # Cumulative Layout Shift
    fcp_ms: float | None = None           # First Contentful Paint
    ttfb_ms: float | None = None          # Time to First Byte
    tbt_ms: float | None = None           # Total Blocking Time
    speed_index_ms: float | None = None


@dataclass(frozen=True)
class LandingPageScore:
    url: str
    performance_score: int          # 0–100 (PageSpeed)
    accessibility_score: int        # 0–100
    seo_score: int                  # 0–100
    best_practices_score: int       # 0–100
    mobile_friendly: bool
    core_web_vitals: CoreWebVitals
    recommendations_pl: list[str]   # 3 Polish-language improvement suggestions from LLM
    scored_at: datetime
    raw_pagespeed: dict = field(default_factory=dict)   # full API response for debugging
