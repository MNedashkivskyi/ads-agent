"""angle_library — the 7 angles as data.

Each angle carries its baseline policy risk and the surfaces it's eligible for.
Adding or tuning an angle is a data change here — no logic anywhere else needs to
move.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface
from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.policy_risk import PolicyRisk

_ALL_SURFACES = (
    AdSurface.HEADLINE,
    AdSurface.DESCRIPTION,
    AdSurface.SITELINK,
    AdSurface.CALLOUT,
    AdSurface.SNIPPET,
)


@dataclass(frozen=True)
class AngleSpec:
    angle: Angle
    description: str
    baseline_policy_risk: PolicyRisk
    eligible_surfaces: tuple[AdSurface, ...]
    guidance: str = ""
    few_shot: tuple[str, ...] = field(default_factory=tuple)


ANGLE_LIBRARY: dict[Angle, AngleSpec] = {
    Angle.PAIN: AngleSpec(
        angle=Angle.PAIN,
        description="Nazwij ból klienta, którego nie może rozwiązać.",
        baseline_policy_risk=PolicyRisk.MEDIUM,  # pain framing can drift into body-shaming
        eligible_surfaces=(AdSurface.HEADLINE, AdSurface.DESCRIPTION),
        guidance="Opisz problem słowami klienta, bez oceniania jego ciała.",
        few_shot=("Cellulit, który nie znika?", "Zmęczenie mimo snu?"),
    ),
    Angle.FAILED_ALTERNATIVE: AngleSpec(
        angle=Angle.FAILED_ALTERNATIVE,
        description="Odwołaj się do tego, co klient już bezskutecznie próbował.",
        baseline_policy_risk=PolicyRisk.LOW,
        eligible_surfaces=(AdSurface.HEADLINE, AdSurface.DESCRIPTION),
        guidance="Diety, ćwiczenia, kremy — co zawiodło?",
        few_shot=("Diety nie pomogły?", "Kremy nie działają?"),
    ),
    Angle.RESULT: AngleSpec(
        angle=Angle.RESULT,
        description="Obiecaj konkretny, wiarygodny efekt.",
        baseline_policy_risk=PolicyRisk.MEDIUM,  # result claims risk overpromising
        eligible_surfaces=_ALL_SURFACES,
        guidance="Konkret i ramy czasowe, bez gwarancji medycznych.",
        few_shot=("Gładsza skóra w 4 tygodnie", "Widoczny efekt po serii"),
    ),
    Angle.SOCIAL_PROOF: AngleSpec(
        angle=Angle.SOCIAL_PROOF,
        description="Pokaż, że inni już zaufali.",
        baseline_policy_risk=PolicyRisk.LOW,
        eligible_surfaces=_ALL_SURFACES,
        guidance="Liczby klientów, opinie, doświadczenie.",
        few_shot=("Zaufało nam 5000 klientek", "15 lat doświadczenia"),
    ),
    Angle.OBJECTION: AngleSpec(
        angle=Angle.OBJECTION,
        description="Rozbrój główną obiekcję przed wizytą.",
        baseline_policy_risk=PolicyRisk.LOW,
        eligible_surfaces=_ALL_SURFACES,
        guidance="Ból, czas, cena, rekonwalescencja.",
        few_shot=("Bez bólu i rekonwalescencji", "Pierwsza konsultacja gratis"),
    ),
    Angle.URGENCY: AngleSpec(
        angle=Angle.URGENCY,
        description="Stwórz uzasadnioną pilność.",
        baseline_policy_risk=PolicyRisk.MEDIUM,  # fake urgency is disallowed
        eligible_surfaces=(AdSurface.HEADLINE, AdSurface.CALLOUT),
        guidance="Prawdziwe terminy/limity, bez fałszywej presji.",
        few_shot=("Ostatnie wolne terminy", "Zapisy na ten tydzień"),
    ),
    Angle.CURIOSITY: AngleSpec(
        angle=Angle.CURIOSITY,
        description="Otwórz pętlę ciekawości pytaniem.",
        baseline_policy_risk=PolicyRisk.LOW,
        eligible_surfaces=(AdSurface.HEADLINE, AdSurface.DESCRIPTION),
        guidance="Pytanie, na które klient chce poznać odpowiedź.",
        few_shot=("Znasz przyczynę cellulitu?", "Dlaczego diety zawodzą?"),
    ),
}


def all_angles() -> list[Angle]:
    return list(ANGLE_LIBRARY.keys())


def spec_for(angle: Angle) -> AngleSpec:
    return ANGLE_LIBRARY[angle]


def angles_for_surface(surface: AdSurface) -> list[Angle]:
    return [a for a, spec in ANGLE_LIBRARY.items() if surface in spec.eligible_surfaces]
