"""Use case: analyze Google Ads account structure and detect structural problems."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.infrastructure.db.models import (
    AdGroupSnapshotModel,
    CampaignSnapshotModel,
)

logger = structlog.get_logger(__name__)

_LOOKBACK_DAYS = 30


async def analyze_account_structure(
    account_id: str,
    session: AsyncSession,
) -> dict:
    """
    Analyze the account's campaign structure and return detected issues and a
    tree view of campaigns with aggregated 30-day metrics.
    """
    log = logger.bind(account_id=account_id)
    log.info("analyze_account_structure.start")

    acct_uuid = uuid.UUID(account_id)
    cutoff = (datetime.now(tz=UTC) - timedelta(days=_LOOKBACK_DAYS)).date()

    # -------------------------------------------------------------------------
    # 1. Aggregate 30-day metrics per campaign
    # -------------------------------------------------------------------------
    stmt = (
        select(
            CampaignSnapshotModel.campaign_id,
            func.max(CampaignSnapshotModel.name).label("campaign_name"),
            func.max(CampaignSnapshotModel.status).label("status"),
            func.sum(CampaignSnapshotModel.cost_micros).label("spend_micros"),
            func.sum(CampaignSnapshotModel.clicks).label("clicks"),
            func.sum(CampaignSnapshotModel.impressions).label("impressions"),
            func.sum(CampaignSnapshotModel.conversions).label("conversions"),
        )
        .where(
            CampaignSnapshotModel.account_id == acct_uuid,
            CampaignSnapshotModel.snapshot_date >= cutoff,
        )
        .group_by(CampaignSnapshotModel.campaign_id)
    )
    rows = (await session.execute(stmt)).all()

    # -------------------------------------------------------------------------
    # 2. Count ad groups per campaign (distinct ad_group_id across the window)
    # -------------------------------------------------------------------------
    ag_stmt = (
        select(
            AdGroupSnapshotModel.campaign_id,
            func.count(func.distinct(AdGroupSnapshotModel.ad_group_id)).label("ad_group_count"),
        )
        .where(
            AdGroupSnapshotModel.account_id == acct_uuid,
            AdGroupSnapshotModel.snapshot_date >= cutoff,
        )
        .group_by(AdGroupSnapshotModel.campaign_id)
    )
    ag_rows = (await session.execute(ag_stmt)).all()
    ag_count_by_campaign: dict[int, int] = {r.campaign_id: r.ad_group_count for r in ag_rows}

    # -------------------------------------------------------------------------
    # 3. Build tree
    # -------------------------------------------------------------------------
    tree: list[dict] = []
    for r in rows:
        tree.append(
            {
                "campaign_id": str(r.campaign_id),
                "campaign_name": r.campaign_name or "",
                "campaign_resource_name": "",  # not stored in CampaignSnapshotModel
                "status": r.status or "",
                "spend_micros": int(r.spend_micros or 0),
                "clicks": int(r.clicks or 0),
                "impressions": int(r.impressions or 0),
                "conversions": float(r.conversions or 0.0),
                "ad_group_count": ag_count_by_campaign.get(r.campaign_id, 0),
            }
        )

    campaign_count = len(tree)

    # -------------------------------------------------------------------------
    # 4. Detect issues
    # -------------------------------------------------------------------------
    issues: list[dict] = []

    # --- 4.1 CAMPAIGN_FRAGMENTATION -------------------------------------------
    # Non-paused campaigns with < 10 clicks in last 30 days
    low_click_campaigns = [t for t in tree if t["status"].upper() != "PAUSED" and t["clicks"] < 10]
    if len(low_click_campaigns) > 5:
        issues.append(
            {
                "type": "CAMPAIGN_FRAGMENTATION",
                "severity": "MEDIUM",
                "description_pl": (
                    f"Wykryto {len(low_click_campaigns)} kampanii z mniej niż 10 kliknięciami "
                    "w ciągu ostatnich 30 dni. Zbyt duże rozdrobnienie kampanii utrudnia "
                    "algorytmom uczenia maszynowego optymalizację stawek."
                ),
                "affected_campaigns": [t["campaign_id"] for t in low_click_campaigns],
                "recommendation_pl": (
                    "Rozważ konsolidację słabo działających kampanii w celu poprawy "
                    "efektywności uczenia maszynowego i obniżenia kosztu kliknięcia."
                ),
            }
        )

    # --- 4.2 DEVICE_PERFORMANCE_DIVERGENCE ------------------------------------
    # Simplified: if > 3 campaigns have < 5 clicks but non-zero spend
    diverging = [t for t in tree if t["clicks"] < 5 and t["spend_micros"] > 0]
    if len(diverging) > 3:
        issues.append(
            {
                "type": "DEVICE_PERFORMANCE_DIVERGENCE",
                "severity": "MEDIUM",
                "description_pl": (
                    f"Wykryto {len(diverging)} kampanii z wydatkami, lecz mniej niż 5 "
                    "kliknięciami — może wskazywać na nierównomierny rozkład budżetu "
                    "między urządzeniami."
                ),
                "affected_campaigns": [t["campaign_id"] for t in diverging],
                "recommendation_pl": (
                    "Przeanalizuj modyfikatory stawek dla urządzeń mobilnych i desktopowych, "
                    "aby równomiernie dystrybuować budżet i poprawić współczynnik kliknięć."
                ),
            }
        )

    # --- 4.3 BUDGET_OPTIMIZATION ----------------------------------------------
    # Campaigns with impressions > 1000, conversions == 0, spend > 500 000 micros
    budget_starved = [
        t
        for t in tree
        if t["impressions"] > 1000 and t["conversions"] == 0.0 and t["spend_micros"] > 500_000
    ]
    if budget_starved:
        issues.append(
            {
                "type": "BUDGET_OPTIMIZATION",
                "severity": "HIGH",
                "description_pl": (
                    f"{len(budget_starved)} kampanii generuje ponad 1 000 wyświetleń "
                    "i znaczące wydatki, nie przynosząc żadnych konwersji. "
                    "Budżet może być wydawany nieefektywnie."
                ),
                "affected_campaigns": [t["campaign_id"] for t in budget_starved],
                "recommendation_pl": (
                    "Sprawdź ustawienia śledzenia konwersji i grupy reklam w tych kampaniach. "
                    "Rozważ wstrzymanie lub przebudowę kampanii bez konwersji."
                ),
            }
        )

    # --- 4.4 CAMPAIGN_BLOAT ---------------------------------------------------
    # Campaigns with > 8 ad groups
    bloated = [t for t in tree if t["ad_group_count"] > 8]
    if bloated:
        issues.append(
            {
                "type": "CAMPAIGN_BLOAT",
                "severity": "MEDIUM",
                "description_pl": (
                    f"{len(bloated)} kampanii zawiera więcej niż 8 grup reklam, "
                    "co może utrudniać zarządzanie i obniżać Wynik Jakości."
                ),
                "affected_campaigns": [t["campaign_id"] for t in bloated],
                "recommendation_pl": (
                    "Rozważ podział przeładowanych kampanii na mniejsze, tematycznie spójne "
                    "jednostki, aby poprawić trafność reklam i Wynik Jakości."
                ),
            }
        )

    # --- 4.5 GEO_PERFORMANCE_REVIEW -------------------------------------------
    if campaign_count > 5:
        issues.append(
            {
                "type": "GEO_PERFORMANCE_REVIEW",
                "severity": "INFO",
                "description_pl": (
                    f"Konto zawiera {campaign_count} kampanii. Przy takiej liczbie kampanii "
                    "warto przeanalizować wyniki geograficzne, aby zidentyfikować regiony "
                    "o wysokim potencjale lub marnotrawstwie budżetu."
                ),
                "affected_campaigns": [t["campaign_id"] for t in tree],
                "recommendation_pl": (
                    "Przejrzyj raport geograficzny i rozważ dodanie modyfikatorów stawek "
                    "lub wykluczeń dla lokalizacji o niskiej efektywności."
                ),
            }
        )

    analyzed_at = datetime.now(tz=UTC).isoformat()

    log.info(
        "analyze_account_structure.done",
        campaign_count=campaign_count,
        issue_count=len(issues),
    )

    return {
        "account_id": account_id,
        "campaign_count": campaign_count,
        "issues": issues,
        "analyzed_at": analyzed_at,
        "tree": tree,
    }
