"""Port (interface) for the vertical template repository (Phase 1, Task 1.2).

Concrete implementations live in ``adcopilot.infrastructure.vertical_templates``.
"""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.launch.vertical_template import VerticalSummary, VerticalTemplate


class VerticalTemplateRepository(Protocol):
    """Read-only access to the in-memory vertical template store."""

    def get_template(self, vertical_id: str) -> VerticalTemplate | None:
        """Return the template for *vertical_id*, or ``None`` if not found."""
        ...

    def list_verticals(self) -> list[VerticalSummary]:
        """Return a summary list of all available verticals for UI rendering."""
        ...

    def get_default_template(self) -> VerticalTemplate:
        """Return the generic fallback template."""
        ...
