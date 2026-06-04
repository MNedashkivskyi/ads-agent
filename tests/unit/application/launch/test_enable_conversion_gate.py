"""Tests for the B5 enable-spend conversion-tracking gate helper + prompt parity."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "goal",
    ["call", "phone_call", "Phone Call", "book", "booking", "purchase", "signup", "sign up", "lead"],
)
def test_goal_requires_tracking_true_for_macro_goals(goal):
    from adcopilot.interfaces.worker.tasks import _goal_requires_tracking

    assert _goal_requires_tracking(goal) is True


@pytest.mark.parametrize("goal", ["visit", "traffic", "awareness", "", None])
def test_goal_requires_tracking_false_for_non_macro(goal):
    from adcopilot.interfaces.worker.tasks import _goal_requires_tracking

    assert _goal_requires_tracking(goal) is False


def test_structure_prompt_matches_seeded_migration():
    """The launch_structure v1 migration content must equal the in-code prompt
    (0057 convention: prompt_versions is the version of record)."""
    import importlib.util
    from pathlib import Path

    from adcopilot.infrastructure.llm.campaign_generator import _STRUCTURE_SYSTEM

    mig_path = (
        Path(__file__).resolve().parents[4]
        / "adcopilot/infrastructure/db/alembic/versions/0067_seed_launch_structure_prompt.py"
    )
    spec = importlib.util.spec_from_file_location("mig0067", mig_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._CONTENT == _STRUCTURE_SYSTEM
