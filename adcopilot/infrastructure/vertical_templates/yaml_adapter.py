"""YAML-backed implementation of VerticalTemplateRepository (Phase 1, Task 1.2).

Templates are loaded once at startup from ``config/verticals/*.yaml``.
The default ('generic') template is used for unknown vertical IDs.
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml
from pydantic import ValidationError

from adcopilot.domain.launch.vertical_template import VerticalSummary, VerticalTemplate

logger = structlog.get_logger(__name__)

_DEFAULT_VERTICAL_ID = "generic"

# Path relative to the repository root (backend/)
_DEFAULT_VERTICALS_DIR = Path(__file__).parent.parent.parent.parent / "config" / "verticals"


class YamlVerticalTemplateAdapter:
    """Loads vertical templates from YAML files in a directory at startup.

    Parameters
    ----------
    verticals_dir:
        Directory containing ``*.yaml`` vertical template files.
        Defaults to ``<repo_root>/config/verticals/``.
    """

    def __init__(self, verticals_dir: Path | None = None) -> None:
        self._dir = verticals_dir or _DEFAULT_VERTICALS_DIR
        self._templates: dict[str, VerticalTemplate] = {}
        self._load()

    # ------------------------------------------------------------------
    # VerticalTemplateRepository protocol
    # ------------------------------------------------------------------

    def get_template(self, vertical_id: str) -> VerticalTemplate | None:
        return self._templates.get(vertical_id)

    def list_verticals(self) -> list[VerticalSummary]:
        return [
            t.to_summary()
            for t in self._templates.values()
            if t.vertical_id != _DEFAULT_VERTICAL_ID
        ]

    def get_default_template(self) -> VerticalTemplate:
        if _DEFAULT_VERTICAL_ID not in self._templates:
            raise RuntimeError(
                f"Default template '{_DEFAULT_VERTICAL_ID}' not found in {self._dir}. "
                "Ensure generic.yaml is present."
            )
        return self._templates[_DEFAULT_VERTICAL_ID]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._dir.exists():
            logger.warning("verticals_dir_missing", dir=str(self._dir))
            return

        for yaml_file in sorted(self._dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                template = VerticalTemplate.model_validate(raw)
                self._templates[template.vertical_id] = template
                logger.debug("vertical_template_loaded", vertical_id=template.vertical_id)
            except (ValidationError, yaml.YAMLError, OSError) as exc:
                logger.error(
                    "vertical_template_load_failed",
                    file=yaml_file.name,
                    error=str(exc),
                )

        logger.info("vertical_templates_loaded", count=len(self._templates))
