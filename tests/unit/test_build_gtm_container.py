"""Unit tests for the premium (per-action) GTM container builder.

Re-asserts every GTM import invariant we learned the hard way, now on the
programmatically-built container instead of the static templates.
"""

from __future__ import annotations

import json
import re

from adcopilot.application.use_cases.build_conversion_plan import (
    ConversionPlanItem,
    build_conversion_plan,
)
from adcopilot.application.use_cases.build_gtm_container import build_gtm_container
from adcopilot.domain.conversion_tracking.setup import ConversionActionTagInfo
from adcopilot.domain.conversion_tracking.trigger_rules import TriggerKind

_VAR_REF_RE = re.compile(r"\{\{([^}]+)\}\}")


def _action(name: str, category: str, suffix: str) -> ConversionActionTagInfo:
    return ConversionActionTagInfo(
        conversion_action_id=int(suffix),
        name=name,
        category=category,
        conversion_id=f"AW-12345678{suffix}",
        conversion_label=f"label_{suffix}",
    )


def _full_plan() -> list[ConversionPlanItem]:
    actions = [
        _action("Zakup", "PURCHASE", "1"),
        _action("Formularz", "LEAD", "2"),
        _action("Telefon", "PHONE_CALL_LEAD", "3"),
        _action("Rejestracja", "SIGNUP", "4"),
        _action("Pobranie", "DOWNLOAD", "5"),
    ]
    return build_conversion_plan(actions, "woocommerce", [])


def _raw_bool_paths(node: object, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(node, bool):
        found.append(path)
    elif isinstance(node, dict):
        for key, value in node.items():
            found.extend(_raw_bool_paths(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            found.extend(_raw_bool_paths(value, f"{path}[{idx}]"))
    return found


def _declared_names(container: dict) -> set[str]:
    cv = container["containerVersion"]
    names = {v["name"] for v in cv.get("variable", [])}
    names |= {b["name"] for b in cv.get("builtInVariable", [])}
    return names


def test_one_tag_and_trigger_per_action() -> None:
    container = build_gtm_container(_full_plan())
    cv = container["containerVersion"]
    assert len(cv["tag"]) == 5
    assert len(cv["trigger"]) == 5
    # tag and trigger ids are unique
    assert len({t["tagId"] for t in cv["tag"]}) == 5
    assert len({t["triggerId"] for t in cv["trigger"]}) == 5


def test_no_raw_booleans() -> None:
    offenders = _raw_bool_paths(build_gtm_container(_full_plan()))
    assert not offenders, f"raw booleans break GTM import at: {offenders}"


def test_all_variable_references_resolve() -> None:
    container = build_gtm_container(_full_plan())
    referenced = set(_VAR_REF_RE.findall(json.dumps(container)))
    unresolved = referenced - _declared_names(container)
    assert not unresolved, f"unresolved references break import: {sorted(unresolved)}"


def test_every_awct_conversion_id_is_a_bare_number() -> None:
    container = build_gtm_container(_full_plan())
    for tag in container["containerVersion"]["tag"]:
        params = {p["key"]: p.get("value") for p in tag["parameter"]}
        assert params["conversionId"].isdigit()
        assert not params["conversionId"].upper().startswith("AW-")
        assert params["conversionLabel"]


def test_value_and_currency_emitted_when_present() -> None:
    item = ConversionPlanItem(
        conversion_action_id=1,
        name="Zakup",
        category="PURCHASE",
        conversion_id="AW-123456789",
        conversion_label="lbl",
        trigger_kind=TriggerKind.PAGE_URL_CONTAINS,
        needs_user_input=False,
        trigger_hint="order-received",
        value=50.0,
        currency="PLN",
    )
    tag = build_gtm_container([item])["containerVersion"]["tag"][0]
    params = {p["key"]: p.get("value") for p in tag["parameter"]}
    assert params["conversionValue"] == "50.0"
    assert params["currencyCode"] == "PLN"


def test_signup_without_hint_uses_nonmatching_placeholder_not_match_all() -> None:
    # A signup with no known success URL must NOT ship an empty CONTAINS filter
    # (which would match every page and mis-fire); it ships a fake placeholder.
    plan = build_conversion_plan([_action("Rejestracja", "SIGNUP", "9")], "custom", [])
    trigger = build_gtm_container(plan)["containerVersion"]["trigger"][0]
    arg1 = trigger["filter"][0]["parameter"][1]["value"]
    assert arg1 != ""
    assert "ZMIEN" in arg1


def test_empty_plan_produces_valid_empty_container() -> None:
    container = build_gtm_container([])
    cv = container["containerVersion"]
    assert cv["tag"] == []
    assert cv["trigger"] == []
    assert "builtInVariable" not in cv
