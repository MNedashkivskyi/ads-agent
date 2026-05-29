"""Integration tests for YamlVerticalTemplateAdapter (Task 1.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adcopilot.application.ports.vertical_template_repository import VerticalTemplateRepository
from adcopilot.infrastructure.vertical_templates.yaml_adapter import YamlVerticalTemplateAdapter


@pytest.fixture()
def tmp_verticals(tmp_path: Path) -> Path:
    """Create a tmp directory with a generic.yaml and a beauty_salon.yaml."""
    generic = {
        "vertical_id": "generic",
        "display_name": "Inna branża",
        "display_emoji": "✏️",
        "language": "pl",
        "competitive_level": "medium",
        "ad_groups": [
            {
                "name_template": "Usługi {city}",
                "keyword_bank": [
                    {"text": "usługi {city}", "match_type": "PHRASE", "priority": "core"},
                    {"text": "kontakt firma", "match_type": "BROAD", "priority": "core"},
                ],
            }
        ],
        "negatives": {
            "universal": ["darmowy", "praca"],
            "vertical_specific": [],
        },
        "bidding_defaults": {
            "micro": {"bidding_strategy": "MAXIMIZE_CLICKS", "max_cpc_limit_pln": 3.0, "daily_budget_ratio": 0.9},
            "mid": {"bidding_strategy": "MAXIMIZE_CONVERSIONS", "max_cpc_limit_pln": 8.0, "daily_budget_ratio": 0.9},
            "growth": {"bidding_strategy": "TARGET_CPA", "max_cpc_limit_pln": 15.0, "daily_budget_ratio": 0.9},
        },
        "extensions": {"sitelinks": [], "callouts": [], "structured_snippet_category": ""},
        "common_services": ["Usługi podstawowe"],
    }
    salon = {
        "vertical_id": "beauty_salon",
        "display_name": "Salon urody",
        "display_emoji": "💅",
        "language": "pl",
        "competitive_level": "medium",
        "ad_groups": [
            {
                "name_template": "Manicure {city}",
                "keyword_bank": [
                    {"text": "manicure {city}", "match_type": "PHRASE", "priority": "core"},
                    {"text": "paznokcie {city}", "match_type": "EXACT", "priority": "core"},
                ],
            }
        ],
        "negatives": {
            "universal": ["darmowy", "praca"],
            "vertical_specific": ["szkolenie fryzjerskie"],
        },
        "bidding_defaults": {
            "micro": {"bidding_strategy": "MAXIMIZE_CLICKS", "max_cpc_limit_pln": 2.0, "daily_budget_ratio": 0.9},
            "mid": {"bidding_strategy": "MAXIMIZE_CONVERSIONS", "max_cpc_limit_pln": 5.0, "daily_budget_ratio": 0.9},
            "growth": {"bidding_strategy": "TARGET_CPA", "max_cpc_limit_pln": 10.0, "daily_budget_ratio": 0.9},
        },
        "extensions": {
            "sitelinks": [{"text": "Cennik", "path": "cennik"}],
            "callouts": ["Szybka wizyta"],
            "structured_snippet_category": "Usługi",
        },
        "common_services": ["Manicure", "Pedicure"],
    }

    (tmp_path / "generic.yaml").write_text(yaml.dump(generic, allow_unicode=True))
    (tmp_path / "beauty_salon.yaml").write_text(yaml.dump(salon, allow_unicode=True))
    return tmp_path


class TestYamlVerticalTemplateAdapter:
    def test_protocol_satisfied(self, tmp_verticals: Path):
        adapter = YamlVerticalTemplateAdapter(tmp_verticals)
        # Static check: adapter satisfies VerticalTemplateRepository protocol
        _: VerticalTemplateRepository = adapter  # type: ignore[assignment]

    def test_get_template_returns_known_vertical(self, tmp_verticals: Path):
        adapter = YamlVerticalTemplateAdapter(tmp_verticals)
        tmpl = adapter.get_template("beauty_salon")
        assert tmpl is not None
        assert tmpl.vertical_id == "beauty_salon"
        assert tmpl.display_emoji == "💅"

    def test_get_template_returns_none_for_unknown(self, tmp_verticals: Path):
        adapter = YamlVerticalTemplateAdapter(tmp_verticals)
        assert adapter.get_template("does_not_exist") is None

    def test_get_default_template_returns_generic(self, tmp_verticals: Path):
        adapter = YamlVerticalTemplateAdapter(tmp_verticals)
        default = adapter.get_default_template()
        assert default.vertical_id == "generic"

    def test_list_verticals_excludes_generic(self, tmp_verticals: Path):
        adapter = YamlVerticalTemplateAdapter(tmp_verticals)
        summaries = adapter.list_verticals()
        ids = [s.vertical_id for s in summaries]
        assert "beauty_salon" in ids
        assert "generic" not in ids

    def test_list_verticals_includes_display_name_and_emoji(self, tmp_verticals: Path):
        adapter = YamlVerticalTemplateAdapter(tmp_verticals)
        salon_summary = next(s for s in adapter.list_verticals() if s.vertical_id == "beauty_salon")
        assert salon_summary.display_name == "Salon urody"
        assert salon_summary.display_emoji == "💅"

    def test_missing_dir_loads_empty(self, tmp_path: Path):
        adapter = YamlVerticalTemplateAdapter(tmp_path / "nonexistent")
        assert adapter.list_verticals() == []

    def test_invalid_yaml_file_is_skipped(self, tmp_verticals: Path):
        (tmp_verticals / "broken.yaml").write_text("vertical_id: bad\nthis: is: not: valid: yaml: !!!\n")
        # Should load without raising; other files still available
        adapter = YamlVerticalTemplateAdapter(tmp_verticals)
        assert adapter.get_template("beauty_salon") is not None

    def test_real_generic_yaml_loads(self):
        """Smoke test: the actual config/verticals/generic.yaml parses correctly."""
        adapter = YamlVerticalTemplateAdapter()
        default = adapter.get_default_template()
        assert default.vertical_id == "generic"
        assert len(default.ad_groups) >= 1
