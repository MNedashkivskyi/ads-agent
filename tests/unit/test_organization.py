"""Unit tests for organization domain + seat limits (Phase 3 / T3.4)."""

from __future__ import annotations

from adcopilot.application.entitlements import max_seats
from adcopilot.domain.entities import PlanTier
from adcopilot.domain.organization import MembershipRole


def test_membership_role_parse() -> None:
    assert MembershipRole.parse("OWNER") is MembershipRole.OWNER
    assert MembershipRole.parse("member") is MembershipRole.MEMBER
    assert MembershipRole.parse("nonsense") is MembershipRole.MEMBER
    assert MembershipRole.parse(None) is MembershipRole.MEMBER


def test_seat_limits_by_plan() -> None:
    assert max_seats(PlanTier.STARTER) == 1
    assert max_seats(PlanTier.PROFESSIONAL) == 1
    assert max_seats(PlanTier.BUSINESS) == 5
    assert max_seats(PlanTier.BUSINESS) > max_seats(PlanTier.PROFESSIONAL)
