"""Stripe billing endpoints."""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import UserId

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["billing"])

_INACTIVE_STATUSES = {"past_due", "canceled", "unpaid"}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    plan: str  # "starter" | "professional" | "business"
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_stripe(settings: Settings) -> Any:
    import stripe as _stripe

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    _stripe.api_key = settings.STRIPE_SECRET_KEY
    return _stripe


def _price_id_for_plan(plan: str, settings: Settings) -> str:
    mapping = {
        "starter": settings.STRIPE_STARTER_PRICE_ID,
        "professional": settings.STRIPE_PRO_PRICE_ID,
        "business": settings.STRIPE_BUSINESS_PRICE_ID,
    }
    price_id = mapping.get(plan.lower())
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")
    return price_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/billing/{user_id}/checkout", response_model=CheckoutResponse)
async def create_checkout(
    user_id: str,
    body: CheckoutRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CheckoutResponse:
    """Create a Stripe Checkout session with 14-day trial."""
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    stripe = _get_stripe(settings)
    price_id = _price_id_for_plan(body.plan, settings)

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")

            # Get or create Stripe customer
            if user.stripe_customer_id:
                customer_id = user.stripe_customer_id
            else:
                customer = stripe.Customer.create(email=user.email, metadata={"user_id": user_id})
                customer_id = customer["id"]
                updated = dataclasses.replace(user, stripe_customer_id=customer_id)
                await repo.save(updated)
                await session.commit()
    finally:
        await engine.dispose()

    session_obj = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        subscription_data={"trial_period_days": 14},
        success_url=body.success_url,
        cancel_url=body.cancel_url,
    )
    return CheckoutResponse(checkout_url=session_obj["url"])


@router.post("/api/billing/{user_id}/portal", response_model=PortalResponse)
async def create_portal(
    user_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PortalResponse:
    """Create a Stripe Customer Portal session."""
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    stripe = _get_stripe(settings)

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
            if not user.stripe_customer_id:
                raise HTTPException(status_code=400, detail="No Stripe customer for this user")
            customer_id = user.stripe_customer_id
    finally:
        await engine.dispose()

    portal = stripe.billing_portal.Session.create(customer=customer_id)
    return PortalResponse(portal_url=portal["url"])


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    stripe_signature: Annotated[str | None, Header(alias="stripe-signature")] = None,
) -> dict[str, str]:
    """Handle Stripe webhook events."""
    import stripe as _stripe

    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    _stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = await request.body()
    try:
        event = _stripe.Webhook.construct_event(  # type: ignore[no-untyped-call]
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except _stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _handle_stripe_event(event, settings)
    return {"status": "ok"}


async def _handle_stripe_event(event: Any, settings: Settings) -> None:
    """Dispatch webhook event to the appropriate handler."""
    event_type: str = event["type"]
    obj = event["data"]["object"]

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await _handle_subscription_event(event_type, obj, settings)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(obj, settings)
    else:
        logger.debug("unhandled stripe event", event_type=event_type)


async def _handle_subscription_event(
    event_type: str, subscription: Any, settings: Settings
) -> None:
    from datetime import UTC, datetime

    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    customer_id: str = subscription["customer"]
    new_status: str = subscription["status"]
    sub_id: str = subscription["id"]

    trial_end_ts = subscription.get("trial_end")
    trial_ends_at = (
        datetime.fromtimestamp(trial_end_ts, tz=UTC) if trial_end_ts else None
    )

    if event_type == "customer.subscription.deleted":
        new_status = "canceled"

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        from sqlalchemy import select

        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(UserModel).where(UserModel.stripe_customer_id == customer_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                logger.warning("stripe webhook: no user for customer", customer_id=customer_id)
                return

            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(str(user_model.id)))
            if user is None:
                return

            updated = dataclasses.replace(
                user,
                subscription_status=new_status,
                subscription_id=sub_id,
                trial_ends_at=trial_ends_at,
            )
            await repo.save(updated)
            await session.commit()
    finally:
        await engine.dispose()

    logger.info(
        "subscription updated",
        customer_id=customer_id,
        event=event_type,
        status=new_status,
    )


async def _handle_payment_failed(invoice: Any, settings: Settings) -> None:
    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    customer_id: str = invoice["customer"]

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        from sqlalchemy import select

        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(UserModel).where(UserModel.stripe_customer_id == customer_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                return

            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(str(user_model.id)))
            if user is None:
                return

            updated = dataclasses.replace(user, subscription_status="past_due")
            await repo.save(updated)
            await session.commit()

            # TODO(phase-0.2): notify user via new notifier when payment fails
    finally:
        await engine.dispose()

    logger.info("payment failed handled", customer_id=customer_id)
