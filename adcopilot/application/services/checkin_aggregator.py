"""Check-in data aggregator.

Fetches real campaign performance metrics from the most recent snapshot
and returns a ``CheckInMetrics`` value object used by ``PostLaunchNotifier``.

Falls back gracefully to zero-valued metrics when no snapshot data is available
(e.g. campaign launched less than 24 hours ago, API quota exceeded).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

_MICROS_PER_PLN = 1_000_000


@dataclass(frozen=True)
class CheckInMetrics:
    clicks: int
    impressions: int
    cost_pln: float
    conversions: int
    ctr: float
    conv_rate: float

    @property
    def is_empty(self) -> bool:
        return self.impressions == 0

    @property
    def performance_label(self) -> str:
        """Return a human-readable performance assessment in Polish."""
        if self.is_empty:
            return "brak danych"
        if self.ctr >= 5.0:
            return "świetny"
        if self.ctr >= 2.0:
            return "dobry"
        if self.ctr >= 0.5:
            return "przeciętny"
        return "niski CTR"


class CheckInAggregator:
    """Aggregates check-in metrics from the snapshot repository."""

    def __init__(self, snapshot_repo) -> None:
        self._repo = snapshot_repo

    async def get_metrics(
        self, account_id: str, campaign_resource_name: str | None
    ) -> CheckInMetrics:
        """Return aggregated performance metrics for a launched campaign.

        Uses the latest available snapshot. Returns zero metrics on any error.
        """
        if campaign_resource_name is None:
            return self._empty()

        try:
            snapshots = await self._repo.list_by_account(account_id, limit=7)
            if not snapshots:
                return self._empty()

            campaign_snaps = [
                s for s in snapshots if s.resource_name == campaign_resource_name
            ]
            if not campaign_snaps:
                return self._empty()

            total_clicks = sum(getattr(s, "clicks", 0) for s in campaign_snaps)
            total_impressions = sum(getattr(s, "impressions", 0) for s in campaign_snaps)
            total_cost_micros = sum(getattr(s, "cost_micros", 0) for s in campaign_snaps)
            total_conversions = int(sum(getattr(s, "conversions", 0.0) for s in campaign_snaps))

            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0
            conv_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0.0

            return CheckInMetrics(
                clicks=total_clicks,
                impressions=total_impressions,
                cost_pln=total_cost_micros / _MICROS_PER_PLN,
                conversions=total_conversions,
                ctr=round(ctr, 2),
                conv_rate=round(conv_rate, 2),
            )
        except Exception as exc:
            logger.warning(
                "checkin_aggregator.failed",
                account_id=account_id,
                error=str(exc),
            )
            return self._empty()

    @staticmethod
    def _empty() -> CheckInMetrics:
        return CheckInMetrics(
            clicks=0,
            impressions=0,
            cost_pln=0.0,
            conversions=0,
            ctr=0.0,
            conv_rate=0.0,
        )


# ---------------------------------------------------------------------------
# 5 check-in message templates (Polish)
# ---------------------------------------------------------------------------

CHECKIN_TEMPLATES: dict[str, str] = {
    "day_3_no_data": (
        "Mija 3 dni od uruchomienia kampanii '{campaign_name}'. "
        "Pierwsze dane z Google Ads pojawią się wkrótce — "
        "zazwyczaj w ciągu 24–48 godzin od uruchomienia. "
        "Śledź postępy w zakładce Dashboard."
    ),
    "day_3_with_data": (
        "Pierwsze 3 dni kampanii '{campaign_name}': "
        "{clicks} kliknięć, {impressions} wyświetleń (CTR {ctr:.1f}%), "
        "wydatki: {cost_pln:.2f} PLN. "
        "{performance_comment}"
    ),
    "day_7_performance": (
        "Tydzień kampanii '{campaign_name}': "
        "{clicks} kliknięć, {impressions} wyświetleń, "
        "CTR {ctr:.1f}%, wydatki: {cost_pln:.2f} PLN. "
        "Konwersje: {conversions}. "
        "{performance_comment} "
        "Jeśli CTR jest niższy niż oczekiwano, rozważ edycję nagłówków reklam."
    ),
    "day_14_insight": (
        "2 tygodnie kampanii '{campaign_name}': "
        "łącznie {clicks} kliknięć przy CTR {ctr:.1f}%. "
        "Koszt na kliknięcie: {cpc_pln:.2f} PLN. "
        "Konwersje: {conversions}. "
        "{performance_comment} "
        "Sprawdź raport wyszukiwanych haseł, by znaleźć nowe słowa kluczowe."
    ),
    "day_30_summary": (
        "Miesięczne podsumowanie kampanii '{campaign_name}': "
        "{clicks} kliknięć, {impressions} wyświetleń, "
        "CTR {ctr:.1f}%, wydatki: {cost_pln:.2f} PLN, "
        "konwersje: {conversions}. "
        "{performance_comment} "
        "Gratulacje — pierwszy miesiąc kampanii za Tobą! "
        "Zapoznaj się z rekomendacjami optymalizacyjnymi w panelu."
    ),
}


def render_checkin_message(
    template_key: str,
    campaign_name: str,
    metrics: CheckInMetrics,
) -> str:
    """Render a check-in message from a named template and metrics."""
    template = CHECKIN_TEMPLATES.get(template_key)
    if template is None:
        return f"Check-in kampanii '{campaign_name}'."

    cpc_pln = metrics.cost_pln / metrics.clicks if metrics.clicks > 0 else 0.0

    performance_comment_map = {
        "świetny": "Świetny wynik — kampania osiąga ponadprzeciętne zaangażowanie!",
        "dobry": "Dobry wynik — kampania pracuje zgodnie z oczekiwaniami.",
        "przeciętny": "Wynik w normie — warto rozważyć optymalizację reklam.",
        "niski CTR": "CTR poniżej normy — rozważ zmianę nagłówków lub doprecyzowanie słów kluczowych.",
        "brak danych": "Dane pojawią się wkrótce — kampania dopiero się rozkręca.",
    }
    performance_comment = performance_comment_map.get(metrics.performance_label, "")

    return template.format(
        campaign_name=campaign_name,
        clicks=metrics.clicks,
        impressions=metrics.impressions,
        cost_pln=metrics.cost_pln,
        conversions=metrics.conversions,
        ctr=metrics.ctr,
        conv_rate=metrics.conv_rate,
        cpc_pln=cpc_pln,
        performance_comment=performance_comment,
    )
