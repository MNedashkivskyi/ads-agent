"""Unit tests for GTM container generation substitution (conversion-id fix)."""

from __future__ import annotations

import json
import re

import pytest

from adcopilot.application.use_cases.generate_gtm_container import generate_gtm_container

_VAR_REF_RE = re.compile(r"\{\{([^}]+)\}\}")


@pytest.mark.parametrize("platform", ["wordpress", "shopify", "woocommerce", "custom", "shoper"])
def test_real_values_leave_no_placeholders(platform: str) -> None:
    container = generate_gtm_container(
        conversion_id="AW-123456789",
        conversion_label="AbC-D_efGhIjk",
        platform=platform,
    )
    serialized = json.dumps(container)

    # A functional container must not ship the template placeholders…
    assert "{{CONVERSION_ID}}" not in serialized
    assert "{{CONVERSION_LABEL}}" not in serialized
    # …and must carry the real conversion identifiers. GTM's awct tag stores the
    # Conversion ID as a bare number, so the "AW-" prefix must be stripped.
    assert "123456789" in serialized
    assert "AW-123456789" not in serialized
    assert "AbC-D_efGhIjk" in serialized


def _awct_tags(container: dict) -> list[dict]:
    return [t for t in container["containerVersion"].get("tag", []) if t.get("type") == "awct"]


def _conversion_ids(container: dict) -> list[str]:
    """Every awct tag's ``conversionId`` parameter value."""
    out: list[str] = []
    for tag in container["containerVersion"].get("tag", []):
        for param in tag.get("parameter", []):
            if param.get("key") == "conversionId":
                out.append(param["value"])
    return out


@pytest.mark.parametrize("platform", ["wordpress", "shopify", "woocommerce", "custom", "shoper"])
def test_every_awct_tag_has_nonempty_conversion_label(platform: str) -> None:
    # GTM's awct tag requires conversionLabel ("Wartość nie może być pusta"); a
    # conversion tag without one (e.g. an all-pages "remarketing" awct) is both
    # rejected on import and would mis-fire a conversion on every page.
    container = generate_gtm_container(
        conversion_id="AW-123456789",
        conversion_label="AbC-D_efGhIjk",
        platform=platform,
    )
    tags = _awct_tags(container)
    assert tags, "expected at least one awct conversion tag"
    for tag in tags:
        params = {p["key"]: p.get("value") for p in tag.get("parameter", [])}
        assert params.get("conversionLabel"), f"awct tag '{tag['name']}' has empty conversionLabel"


@pytest.mark.parametrize(
    ("conversion_id_in", "expected"),
    [("AW-709309053", "709309053"), ("709309053", "709309053"), ("aw-555", "555")],
)
def test_awct_conversion_id_is_a_bare_number(conversion_id_in: str, expected: str) -> None:
    # GTM rejects "AW-..." in the conversionId field ("Wartość musi być dodatnią
    # liczbą całkowitą") — it must be the numeric id only.
    container = generate_gtm_container(
        conversion_id=conversion_id_in,
        conversion_label="AbC-D_efGhIjk",
        platform="custom",
    )
    ids = _conversion_ids(container)
    assert ids, "expected at least one awct conversionId parameter"
    for value in ids:
        assert value == expected
        assert not value.upper().startswith("AW-")


def _raw_bool_paths(node: object, path: str = "$") -> list[str]:
    """Return JSON paths of any raw boolean values in a GTM container.

    GTM's export format wraps every boolean as a Parameter object
    ``{"type": "BOOLEAN", "value": "true"}`` — a bare ``true``/``false`` makes
    the importer fail with "Argument is not an object: true".
    """
    found: list[str] = []
    if isinstance(node, bool):  # bool before int — bool is a subclass of int
        found.append(path)
    elif isinstance(node, dict):
        for key, value in node.items():
            found.extend(_raw_bool_paths(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            found.extend(_raw_bool_paths(value, f"{path}[{idx}]"))
    return found


@pytest.mark.parametrize("platform", ["wordpress", "shopify", "woocommerce", "custom", "shoper"])
def test_no_raw_booleans_so_gtm_import_succeeds(platform: str) -> None:
    container = generate_gtm_container(
        conversion_id="AW-123456789",
        conversion_label="AbC-D_efGhIjk",
        platform=platform,
    )
    offenders = _raw_bool_paths(container)
    assert not offenders, f"raw booleans break GTM import at: {offenders}"


def _declared_names(container: dict) -> set[str]:
    """Names GTM can resolve: user-defined variables + declared built-ins."""
    cv = container["containerVersion"]
    names: set[str] = set()
    for v in cv.get("variable", []):
        names.add(v["name"])
    for b in cv.get("builtInVariable", []):
        names.add(b["name"])
    return names


@pytest.mark.parametrize("platform", ["wordpress", "shopify", "woocommerce", "custom", "shoper"])
def test_all_variable_references_resolve(platform: str) -> None:
    """Every {{ref}} must point at a declared variable/built-in.

    An undeclared reference (e.g. {{Page URL}} with no PAGE_URL built-in) makes
    GTM reject the import with "Nie znaleziono" / "Not found". The real
    conversion id/label placeholders are substituted before this point, so any
    {{...}} left in the serialized container must resolve.
    """
    container = generate_gtm_container(
        conversion_id="AW-123456789",
        conversion_label="AbC-D_efGhIjk",
        platform=platform,
    )
    referenced = set(_VAR_REF_RE.findall(json.dumps(container)))
    unresolved = referenced - _declared_names(container)
    assert not unresolved, f"unresolved GTM variable references break import: {sorted(unresolved)}"
