"""LAUNCH-004: admin access must fail closed when ADMIN_USER_IDS is empty."""

from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_empty_admin_list_denies_everyone() -> None:
    from adcopilot.config import Settings
    from adcopilot.interfaces.api.admin import _check_admin

    settings = Settings(ADMIN_USER_IDS="")
    with pytest.raises(HTTPException) as exc:
        _check_admin("any-user", settings)
    assert exc.value.status_code == 403


def test_configured_admin_passes_others_denied() -> None:
    from adcopilot.config import Settings
    from adcopilot.interfaces.api.admin import _check_admin

    settings = Settings(ADMIN_USER_IDS="admin-1, admin-2")
    _check_admin("admin-1", settings)  # no raise
    with pytest.raises(HTTPException) as exc:
        _check_admin("admin-3", settings)
    assert exc.value.status_code == 403
