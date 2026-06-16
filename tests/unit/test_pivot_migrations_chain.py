"""Migration-chain tests for the optimization-pivot migrations (T6.1).

Verifies the new migrations (0075-0078) form a correct, linear, reversible
chain. Raising the Professional account limit is config-only (no data
migration), so the only data migration is the idempotent personal-org backfill
in 0078 — these tests guard its revision wiring and reversibility.
"""

from __future__ import annotations

import importlib

import pytest

_VERSIONS_PKG = "adcopilot.infrastructure.db.alembic.versions"

# (module, expected revision, expected down_revision)
_CHAIN = [
    ("0075_deprecate_launch_prompts", "0075", "0074"),
    ("0076_auto_apply_settings", "0076", "0075"),
    ("0077_api_keys", "0077", "0076"),
    ("0078_organizations_team_seats", "0078", "0077"),
]


@pytest.mark.parametrize("module_name,revision,down_revision", _CHAIN)
def test_revision_wiring(module_name: str, revision: str, down_revision: str) -> None:
    mod = importlib.import_module(f"{_VERSIONS_PKG}.{module_name}")
    assert mod.revision == revision
    assert mod.down_revision == down_revision


@pytest.mark.parametrize("module_name,_rev,_down", _CHAIN)
def test_upgrade_and_downgrade_exist(module_name: str, _rev: str, _down: str) -> None:
    """Every pivot migration must be reversible (have an upgrade + downgrade)."""
    mod = importlib.import_module(f"{_VERSIONS_PKG}.{module_name}")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_chain_is_linear_and_contiguous() -> None:
    revisions = [c[1] for c in _CHAIN]
    downs = [c[2] for c in _CHAIN]
    # Each migration's down_revision is the previous migration's revision.
    assert downs[1:] == revisions[:-1]
