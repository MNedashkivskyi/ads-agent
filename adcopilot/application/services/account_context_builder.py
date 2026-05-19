"""AccountContextBuilder — aggregates account metrics into a structured dict for LLM injection."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from adcopilot.application.ports.audit_log_repository import AuditLogRepository
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.snapshot_repository import SnapshotRepository
from adcopilot.domain.entities import AccountId

logger = structlog.get_logger(__name__)

_MAX_TOKENS = 3000
_PLN = 1_000_000  # micros → PLN


def _micros_to_pln(micros: int | float) -> float:
    return round(micros / _PLN, 2)


def _safe_cpc(cost_micros: int | float, clicks: int) -> float:
    if clicks == 0:
        return 0.0
    return round(cost_micros / clicks / _PLN, 2)


def _safe_roas(conv_value: float, cost_micros: int | float) -> float:
    if cost_micros == 0:
        return 0.0
    return round(conv_value / (cost_micros / _PLN), 2)


def _safe_cpa(cost_micros: int | float, conversions: float) -> float:
    if conversions == 0:
        return 0.0
    return round(cost_micros / conversions / _PLN, 2)


def _delta_pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    # Rough approximation: 1 token ≈ 4 chars
    max_chars = max_tokens * 4
    if len(text) > max_chars:
        return text[:max_chars] + "...[obcięto]"
    return text


class AccountContextBuilder:
    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        rec_repo: RecommendationRepository,
        audit_log_repo: AuditLogRepository,
    ) -> None:
        self._snapshot_repo = snapshot_repo
        self._rec_repo = rec_repo
        self._audit_log_repo = audit_log_repo

    async def build(self, account_id: AccountId) -> dict[str, Any]:
        """Build a structured context dict for the given account."""
        now = datetime.now(UTC)
        since_7d = now - timedelta(days=7)

        latest_date = await self._snapshot_repo.get_latest_snapshot_date(account_id)
        if latest_date is None:
            return _empty_context(account_id)

        current_campaigns = await self._snapshot_repo.get_campaigns_by_date(account_id, latest_date)

        # Week-over-week comparison (7 days prior)
        prior_date = latest_date - timedelta(days=7)
        prior_campaigns = await self._snapshot_repo.get_campaigns_by_date(account_id, prior_date)

        # Aggregate current metrics
        total_cost = sum(c.cost_micros for c in current_campaigns)
        total_clicks = sum(c.clicks for c in current_campaigns)
        total_impressions = sum(c.impressions for c in current_campaigns)
        total_conversions = sum(c.conversions for c in current_campaigns)
        total_conv_value = sum(c.conv_value for c in current_campaigns)
        total_budget = sum(c.budget_micros for c in current_campaigns)

        # Aggregate prior metrics
        prior_cost = sum(c.cost_micros for c in prior_campaigns)
        prior_clicks = sum(c.clicks for c in prior_campaigns)
        prior_conversions = sum(c.conversions for c in prior_campaigns)
        prior_conv_value = sum(c.conv_value for c in prior_campaigns)

        # Week-over-week deltas
        deltas = {
            "cost_pct": _delta_pct(total_cost, prior_cost),
            "clicks_pct": _delta_pct(total_clicks, prior_clicks),
            "conversions_pct": _delta_pct(total_conversions, prior_conversions),
            "roas_pct": _delta_pct(
                _safe_roas(total_conv_value, total_cost),
                _safe_roas(prior_conv_value, prior_cost),
            ),
        }

        # Active alerts (PENDING recommendations)
        pending_recs = await self._rec_repo.list_pending(account_id)
        alerts = [
            {"kind": r.kind.value, "severity": r.severity.value}
            for r in pending_recs[:10]
        ]

        # Top 3 recently executed recommendations
        recent_logs = await self._audit_log_repo.list_recent_executes([account_id], since_7d)
        top_executed = [
            {
                "kind": log.payload.get("kind", "UNKNOWN"),
                "executed_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in recent_logs[:3]
        ]

        # Campaign-level breakdown (top 5 by spend)
        top_campaigns = sorted(current_campaigns, key=lambda c: c.cost_micros, reverse=True)[:5]
        campaign_breakdown = [
            {
                "name": c.name,
                "status": c.status,
                "spend_pln": _micros_to_pln(c.cost_micros),
                "budget_pln": _micros_to_pln(c.budget_micros),
                "budget_utilisation_pct": round(c.cost_micros / c.budget_micros * 100, 1) if c.budget_micros else None,
                "clicks": c.clicks,
                "conversions": c.conversions,
                "cpc_pln": _safe_cpc(c.cost_micros, c.clicks),
                "roas": _safe_roas(c.conv_value, c.cost_micros),
            }
            for c in top_campaigns
        ]

        ctx: dict[str, Any] = {
            "account_id": str(account_id),
            "snapshot_date": latest_date.isoformat(),
            "summary": {
                "total_spend_pln": _micros_to_pln(total_cost),
                "total_budget_pln": _micros_to_pln(total_budget),
                "budget_utilisation_pct": round(total_cost / total_budget * 100, 1) if total_budget else None,
                "total_clicks": total_clicks,
                "total_impressions": total_impressions,
                "total_conversions": total_conversions,
                "cpc_pln": _safe_cpc(total_cost, total_clicks),
                "cpa_pln": _safe_cpa(total_cost, total_conversions),
                "roas": _safe_roas(total_conv_value, total_cost),
                "active_campaigns": len([c for c in current_campaigns if c.status == "ENABLED"]),
                "paused_campaigns": len([c for c in current_campaigns if c.status == "PAUSED"]),
            },
            "week_over_week_deltas": deltas,
            "top_campaigns": campaign_breakdown,
            "active_alerts": alerts,
            "recent_executions": top_executed,
        }

        # Enforce token budget
        serialised = json.dumps(ctx, ensure_ascii=False)
        if len(serialised) > _MAX_TOKENS * 4:
            ctx["top_campaigns"] = campaign_breakdown[:3]
            ctx["active_alerts"] = alerts[:5]
            logger.info("account_context.truncated", account_id=str(account_id))

        return ctx


def _empty_context(account_id: AccountId) -> dict[str, Any]:
    return {
        "account_id": str(account_id),
        "snapshot_date": None,
        "summary": None,
        "week_over_week_deltas": {},
        "top_campaigns": [],
        "active_alerts": [],
        "recent_executions": [],
        "note": "Brak danych — konto nie posiada żadnych migawek.",
    }
