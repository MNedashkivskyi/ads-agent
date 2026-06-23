"""Unit tests for dedupe_recommendations (GET /recommendations dedup filter)."""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.interfaces.api.users import dedupe_recommendations


@dataclass
class _Row:
    """Minimal stand-in for RecommendationModel."""

    id: str
    account_id: str = "acc-1"
    kind: str = "PAUSE_KEYWORD"
    severity: str = "HIGH"
    status: str = "PENDING"
    target_hash: str = "hash-a"


def test_collapses_identical_duplicates_keeping_first() -> None:
    """Rows sharing the full key collapse to the first (newest) one."""
    rows = [_Row(id="new"), _Row(id="old")]
    result = dedupe_recommendations(rows)
    assert [r.id for r in result] == ["new"]


def test_keeps_rows_with_different_target_hash() -> None:
    """Same kind/severity/status but different target are NOT duplicates."""
    rows = [_Row(id="a", target_hash="hash-a"), _Row(id="b", target_hash="hash-b")]
    result = dedupe_recommendations(rows)
    assert [r.id for r in result] == ["a", "b"]


def test_keeps_rows_differing_on_each_key_field() -> None:
    """Differing on any single key field keeps both rows."""
    base = _Row(id="base")
    variants = [
        base,
        _Row(id="acc", account_id="acc-2"),
        _Row(id="kind", kind="ADD_NEGATIVE_KEYWORD"),
        _Row(id="sev", severity="LOW"),
        _Row(id="status", status="DECLINED"),
    ]
    result = dedupe_recommendations(variants)
    assert [r.id for r in result] == ["base", "acc", "kind", "sev", "status"]


def test_preserves_order_of_first_occurrences() -> None:
    """Surviving rows keep their original relative order."""
    rows = [
        _Row(id="1", target_hash="x"),
        _Row(id="2", target_hash="y"),
        _Row(id="3", target_hash="x"),  # dup of 1
        _Row(id="4", target_hash="z"),
    ]
    result = dedupe_recommendations(rows)
    assert [r.id for r in result] == ["1", "2", "4"]


def test_empty_list() -> None:
    assert dedupe_recommendations([]) == []


def test_missing_target_hash_treated_as_none() -> None:
    """Rows without a target_hash attribute dedup on None without erroring."""

    class _NoHash:
        def __init__(self, rid: str) -> None:
            self.id = rid
            self.account_id = "acc-1"
            self.kind = "PAUSE_KEYWORD"
            self.severity = "HIGH"
            self.status = "PENDING"

    rows = [_NoHash("a"), _NoHash("b")]
    result = dedupe_recommendations(rows)
    assert [r.id for r in result] == ["a"]
