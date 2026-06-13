"""HookSet — aggregate that assembles and validates a complete RSA.

A Responsive Search Ad needs at least 3 headlines and 2 descriptions. The set
holds the selected hooks across surfaces, validates that minimum, pins the
strongest hook to headline slot 1, and renders the Google Ads asset payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookCandidate

MIN_HEADLINES = 3
MIN_DESCRIPTIONS = 2
PINNED_HEADLINE_SLOT = "HEADLINE_1"


@dataclass
class HookSet:
    candidates: list[HookCandidate] = field(default_factory=list)

    def by_surface(self, surface: AdSurface) -> list[HookCandidate]:
        return [c for c in self.candidates if c.surface is surface]

    @property
    def headlines(self) -> list[HookCandidate]:
        return self.by_surface(AdSurface.HEADLINE)

    @property
    def descriptions(self) -> list[HookCandidate]:
        return self.by_surface(AdSurface.DESCRIPTION)

    def is_valid_rsa(self) -> bool:
        return len(self.headlines) >= MIN_HEADLINES and len(self.descriptions) >= MIN_DESCRIPTIONS

    def validate(self) -> None:
        if len(self.headlines) < MIN_HEADLINES:
            raise ValueError(
                f"RSA needs ≥{MIN_HEADLINES} headlines, has {len(self.headlines)}"
            )
        if len(self.descriptions) < MIN_DESCRIPTIONS:
            raise ValueError(
                f"RSA needs ≥{MIN_DESCRIPTIONS} descriptions, has {len(self.descriptions)}"
            )

    def pin_top_headline(self) -> HookCandidate | None:
        """Pin the highest-scoring headline to slot 1; return it."""
        headlines = sorted(self.headlines, key=lambda c: c.final_score, reverse=True)
        if not headlines:
            return None
        top = headlines[0]
        top.pinned_slot = PINNED_HEADLINE_SLOT
        return top

    def to_rsa_payload(self) -> dict:
        """Render the Google Ads RSA asset payload, with pinning preserved."""
        self.validate()

        def _assets(surface: AdSurface) -> list[dict]:
            out = []
            for c in sorted(self.by_surface(surface), key=lambda x: x.final_score, reverse=True):
                asset: dict = {"text": c.text, "angle": c.angle.value}
                if c.pinned_slot:
                    asset["pinned_field"] = c.pinned_slot
                out.append(asset)
            return out

        return {
            "headlines": _assets(AdSurface.HEADLINE),
            "descriptions": _assets(AdSurface.DESCRIPTION),
            "sitelinks": _assets(AdSurface.SITELINK),
            "callouts": _assets(AdSurface.CALLOUT),
            "structured_snippets": _assets(AdSurface.SNIPPET),
        }
