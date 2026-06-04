"""Repository for per-account business economics (Phase 5)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.business_economics import BusinessEconomics
from adcopilot.infrastructure.db.models import BusinessEconomicsModel


def _to_domain(m: BusinessEconomicsModel) -> BusinessEconomics:
    return BusinessEconomics(
        account_id=str(m.account_id),
        avg_order_value=float(m.avg_order_value) if m.avg_order_value is not None else None,
        profit_margin_pct=float(m.profit_margin_pct) if m.profit_margin_pct is not None else None,
        customer_ltv=float(m.customer_ltv) if m.customer_ltv is not None else None,
        target_roas=float(m.target_roas) if m.target_roas is not None else None,
        default_lead_value=float(m.default_lead_value)
        if m.default_lead_value is not None
        else None,
        currency_code=m.currency_code,
        primary_goal=m.primary_goal,
        target_cpa=float(m.target_cpa) if m.target_cpa is not None else None,
        monthly_conversion_capacity=m.monthly_conversion_capacity,
        brand_terms=list(m.brand_terms or []),
        excluded_terms=list(m.excluded_terms or []),
        updated_at=m.updated_at,
    )


class BusinessEconomicsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: str) -> BusinessEconomics | None:
        row = (
            await self._session.execute(
                select(BusinessEconomicsModel).where(
                    BusinessEconomicsModel.account_id == uuid.UUID(account_id)
                )
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def upsert(self, econ: BusinessEconomics) -> None:
        values = {
            "account_id": uuid.UUID(econ.account_id),
            "avg_order_value": econ.avg_order_value,
            "profit_margin_pct": econ.profit_margin_pct,
            "customer_ltv": econ.customer_ltv,
            "target_roas": econ.target_roas,
            "default_lead_value": econ.default_lead_value,
            "currency_code": econ.currency_code,
            "primary_goal": econ.primary_goal,
            "target_cpa": econ.target_cpa,
            "monthly_conversion_capacity": econ.monthly_conversion_capacity,
            "brand_terms": list(econ.brand_terms or []),
            "excluded_terms": list(econ.excluded_terms or []),
        }
        stmt = insert(BusinessEconomicsModel).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in values if k != "account_id"}
        stmt = stmt.on_conflict_do_update(index_elements=["account_id"], set_=update_cols)
        await self._session.execute(stmt)
