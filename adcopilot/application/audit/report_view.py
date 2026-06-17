"""Free preview vs. gated full findings (Audit Funnel T2.2).

The public reveal shows the headline plus the top few findings; the full list
(and the PDF) is gated behind the share token or signup. This pure helper picks
the preview set so the endpoint and tests agree on it.
"""

from __future__ import annotations

from adcopilot.domain.audit import WasteFinding

FREE_PREVIEW_LIMIT = 3


def preview_findings(
    findings: list[WasteFinding], limit: int = FREE_PREVIEW_LIMIT
) -> tuple[list[WasteFinding], int]:
    """Return the top ``limit`` findings by amount plus the count withheld.

    Findings with a złoty amount rank first (largest first); qualitative
    findings (no amount) sort last.
    """
    ordered = sorted(findings, key=lambda f: (f.amount_micros is None, -(f.amount_micros or 0)))
    shown = ordered[:limit]
    return shown, max(0, len(findings) - len(shown))
