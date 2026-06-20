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
    # …and must carry the real conversion identifiers.
    assert "AW-123456789" in serialized
    assert "AbC-D_efGhIjk" in serialized


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
