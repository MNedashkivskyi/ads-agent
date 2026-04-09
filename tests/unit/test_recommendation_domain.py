"""Unit tests for recommendation domain model and compute_target_hash."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
    compute_target_hash,
)

# ---------------------------------------------------------------------------
# compute_target_hash
# ---------------------------------------------------------------------------


def test_hash_is_stable() -> None:
    """Same dict always produces the same hash."""
    target = {"campaign_id": 123, "ad_group_id": 456}
    assert compute_target_hash(target) == compute_target_hash(target)


def test_hash_is_stable_across_key_order() -> None:
    """Key insertion order does not affect the hash."""
    t1 = {"a": 1, "b": 2}
    t2 = {"b": 2, "a": 1}
    assert compute_target_hash(t1) == compute_target_hash(t2)


def test_different_inputs_produce_different_hashes() -> None:
    """Different targets must not collide."""
    t1 = {"campaign_id": 1}
    t2 = {"campaign_id": 2}
    assert compute_target_hash(t1) != compute_target_hash(t2)


def test_hash_length_is_64_chars() -> None:
    """SHA-256 hex digest is always 64 characters."""
    assert len(compute_target_hash({})) == 64
    assert len(compute_target_hash({"x": "y"})) == 64


def test_nested_dict_produces_stable_hash() -> None:
    """Nested structures are hashed consistently."""
    t = {"outer": {"inner": [1, 2, 3]}}
    assert compute_target_hash(t) == compute_target_hash(t)


def test_empty_dict_has_deterministic_hash() -> None:
    """Empty target has a stable, unique hash."""
    h = compute_target_hash({})
    assert h == compute_target_hash({})
    assert h != compute_target_hash({"x": 1})


# ---------------------------------------------------------------------------
# Recommendation dataclass
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 9, tzinfo=UTC)
_ACCOUNT = AccountId("acct-1")


def _make_rec(**kwargs: object) -> Recommendation:
    defaults: dict[str, object] = {
        "id": RecommendationId(str(uuid.uuid4())),
        "account_id": _ACCOUNT,
        "kind": RecommendationKind.PAUSE_KEYWORD,
        "severity": RecommendationSeverity.HIGH,
        "target": {"criterion_id": 1},
        "payload": {"ad_group_id": 2},
        "estimated_monthly_savings_micros": 5_000_000,
        "evidence": {"cost_micros": 10_000_000},
        "created_at": _NOW,
        "status": RecommendationStatus.PENDING,
    }
    defaults.update(kwargs)
    return Recommendation(**defaults)  # type: ignore[arg-type]


def test_recommendation_target_hash_auto_computed() -> None:
    """target_hash is populated automatically via __post_init__."""
    rec = _make_rec(target={"campaign_id": 99})
    assert rec.target_hash == compute_target_hash({"campaign_id": 99})


def test_recommendation_explicit_target_hash_preserved() -> None:
    """If target_hash is provided, it is not overwritten."""
    custom_hash = "a" * 64
    rec = _make_rec(target={"x": 1}, target_hash=custom_hash)
    assert rec.target_hash == custom_hash


def test_recommendation_is_frozen() -> None:
    """Recommendation is immutable."""
    rec = _make_rec()
    try:
        rec.status = RecommendationStatus.APPROVED  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except Exception as exc:
        assert "frozen" in str(exc).lower() or "FrozenInstanceError" in type(exc).__name__
