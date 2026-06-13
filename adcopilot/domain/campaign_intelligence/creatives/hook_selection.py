"""hook_selection — pick the top hooks per surface with angle diversity (pure).

Greedy round-robin by angle: within a surface, repeatedly take the highest-scoring
remaining hook from each angle in turn. This guarantees the selection never
collapses onto a single angle when alternatives exist, while still favouring the
strongest hooks. Deterministic.
"""

from __future__ import annotations

from collections import defaultdict

from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookCandidate


def select_for_surface(candidates: list[HookCandidate], k: int) -> list[HookCandidate]:
    """Select up to *k* hooks (all the same surface) maximising angle diversity."""
    by_angle: dict[str, list[HookCandidate]] = defaultdict(list)
    for c in candidates:
        by_angle[c.angle.value].append(c)
    for group in by_angle.values():
        group.sort(key=lambda c: c.final_score, reverse=True)

    # Angles ordered by their best hook's score, so stronger angles go first.
    angle_order = sorted(
        by_angle,
        key=lambda a: (by_angle[a][0].final_score if by_angle[a] else 0.0),
        reverse=True,
    )

    selected: list[HookCandidate] = []
    cursors = dict.fromkeys(angle_order, 0)
    while len(selected) < k:
        progressed = False
        for angle in angle_order:
            if len(selected) >= k:
                break
            idx = cursors[angle]
            group = by_angle[angle]
            if idx < len(group):
                selected.append(group[idx])
                cursors[angle] = idx + 1
                progressed = True
        if not progressed:
            break
    return selected


def select_hooks(
    candidates: list[HookCandidate], top_k_per_surface: dict[AdSurface, int]
) -> list[HookCandidate]:
    """Select hooks across surfaces using per-surface diversity-aware picks."""
    out: list[HookCandidate] = []
    for surface, k in top_k_per_surface.items():
        surface_candidates = [c for c in candidates if c.surface is surface]
        out.extend(select_for_surface(surface_candidates, k))
    return out
