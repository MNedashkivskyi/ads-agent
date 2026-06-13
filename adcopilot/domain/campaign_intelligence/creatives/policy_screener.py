"""policy_screener — heuristic disapproval-risk screen (pure).

Catches the two highest-cost failure modes before a hook is ever shown to a
judge or shipped: **body-shaming** (Google's personalized-ads / sensitive-event
policy) and **medical/efficacy overclaims** (unverifiable health claims). Lesser
issues (shouting caps, excessive punctuation, superlatives) raise MEDIUM. The
angle's baseline risk is folded in so an inherently riskier angle starts higher.

Pure and deterministic — no I/O.
"""

from __future__ import annotations

import re

from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.angle_library import spec_for
from adcopilot.domain.campaign_intelligence.creatives.policy_risk import PolicyFinding, PolicyRisk

# Body-shaming / sensitive-trait language (PL + EN). HIGH risk.
_BODY_SHAMING = (
    "grube uda",
    "grube nogi",
    "brzydki",
    "brzydka",
    "wstydzisz się",
    "wstydź się",
    "twoja wina",
    "obrzydliwy",
    "ugly",
    "fat thighs",
    "you should be ashamed",
    "disgusting",
)

# Medical / efficacy overclaims (PL + EN). HIGH risk.
_MEDICAL_OVERCLAIM = (
    "wyleczy",
    "wyleczymy",
    "100% skuteczności",
    "100% skuteczność",
    "gwarantujemy efekt",
    "gwarantowany efekt",
    "gwarancja wyleczenia",
    "całkowicie usuwa",
    "trwale usuwa",
    "cure",
    "cures",
    "guaranteed results",
    "100% effective",
    "miracle",
    "cudowny lek",
)

# Softer issues → MEDIUM.
_SUPERLATIVES = ("najlepszy", "najlepsza", "numer 1", "nr 1", "#1", "best ever")
_MAX_EXCLAMATIONS = 1


def screen(text: str, angle: Angle | None = None) -> PolicyFinding:
    """Return the policy finding for *text*, folding in the angle baseline."""
    lowered = text.lower()
    risks: list[tuple[PolicyRisk, str]] = []

    for term in _BODY_SHAMING:
        if term in lowered:
            risks.append((PolicyRisk.HIGH, f"Możliwe body-shaming: '{term}'"))
            break
    for term in _MEDICAL_OVERCLAIM:
        if term in lowered:
            risks.append((PolicyRisk.HIGH, f"Nieweryfikowalne obietnice medyczne: '{term}'"))
            break
    for term in _SUPERLATIVES:
        if term in lowered:
            risks.append((PolicyRisk.MEDIUM, f"Superlatyw wymagający dowodu: '{term}'"))
            break
    if text.count("!") > _MAX_EXCLAMATIONS:
        risks.append((PolicyRisk.MEDIUM, "Nadmiar wykrzykników"))
    if _has_shouting(text):
        risks.append((PolicyRisk.MEDIUM, "Krzyk (CAPS LOCK)"))

    if angle is not None:
        risks.append((spec_for(angle).baseline_policy_risk, "Bazowe ryzyko kąta"))

    if not risks:
        return PolicyFinding.low()
    worst = max(risks, key=lambda r: r[0].rank)
    # Prefer the reason of the worst risk; if it's just the angle baseline (LOW),
    # there's effectively no finding to report.
    if worst[0] is PolicyRisk.LOW:
        return PolicyFinding.low()
    return PolicyFinding(worst[0], worst[1])


def _has_shouting(text: str) -> bool:
    letters = re.sub(r"[^A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", "", text)
    if len(letters) < 5:
        return False
    uppercase = sum(1 for ch in letters if ch.isupper())
    return uppercase / len(letters) > 0.7
