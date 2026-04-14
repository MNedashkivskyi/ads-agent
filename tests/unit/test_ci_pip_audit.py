"""Tests for :mod:`scripts.ci_pip_audit`.

We test only the pure logic — severity mapping, OSV payload parsing,
report flattening, and the final blocking decision.  The actual
``pip-audit`` invocation is covered in CI itself; mocking the whole
subprocess run here would mostly be a tautology.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

import pytest


def _load_script() -> Any:
    """Import scripts/ci_pip_audit.py under the name ``ci_pip_audit``.

    ``scripts/`` is not a package so we use importlib spec loading.
    """
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    path = root / "scripts" / "ci_pip_audit.py"
    spec = importlib.util.spec_from_file_location("ci_pip_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_pip_audit"] = module
    spec.loader.exec_module(module)
    return module


audit = _load_script()


# ---------------------------------------------------------------------------
# score_to_label — CVSS v3 severity bands.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, "NONE"),
        (0.1, "LOW"),
        (3.9, "LOW"),
        (4.0, "MEDIUM"),
        (6.9, "MEDIUM"),
        (7.0, "HIGH"),
        (8.9, "HIGH"),
        (9.0, "CRITICAL"),
        (9.8, "CRITICAL"),
        (10.0, "CRITICAL"),
    ],
)
def test_score_to_label(score: float, expected: str) -> None:
    assert audit.score_to_label(score) == expected


# ---------------------------------------------------------------------------
# _extract_cvss_score — OSV payload variants.
# ---------------------------------------------------------------------------


def test_extract_score_from_database_specific_numeric() -> None:
    payload = {"database_specific": {"severity": 8.5}}
    assert audit._extract_cvss_score(payload) == 8.5


def test_extract_score_from_database_specific_label_critical() -> None:
    payload = {"database_specific": {"severity": "CRITICAL"}}
    score = audit._extract_cvss_score(payload)
    assert score is not None and score >= 9.0


def test_extract_score_from_database_specific_label_high() -> None:
    payload = {"database_specific": {"severity": "high"}}
    score = audit._extract_cvss_score(payload)
    assert score is not None and 7.0 <= score < 9.0


def test_extract_score_takes_max_over_affected_entries() -> None:
    payload = {
        "affected": [
            {"database_specific": {"cvss_v3_base_score": 4.2}},
            {"database_specific": {"cvss_v3_base_score": 9.1}},
            {"database_specific": {"cvss_v3_base_score": 7.0}},
        ]
    }
    assert audit._extract_cvss_score(payload) == 9.1


def test_extract_score_returns_none_when_nothing_usable() -> None:
    payload = {"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L"}]}
    assert audit._extract_cvss_score(payload) is None


def test_extract_score_empty_payload_returns_none() -> None:
    assert audit._extract_cvss_score({}) is None


# ---------------------------------------------------------------------------
# collect_vulnerabilities + has_blocking — decision logic.
# ---------------------------------------------------------------------------


def _make_vuln(label: str, score: float | None = None) -> Any:
    return audit.Vulnerability(
        package="pkg",
        version="1.0.0",
        vuln_id="GHSA-test",
        aliases=(),
        fix_versions=("1.0.1",),
        severity_label=label,
        severity_score=score,
    )


def test_has_blocking_critical() -> None:
    assert audit.has_blocking([_make_vuln("CRITICAL", 9.5)]) is True


def test_has_blocking_high() -> None:
    assert audit.has_blocking([_make_vuln("HIGH", 7.5)]) is True


def test_no_blocking_for_medium_or_low() -> None:
    assert audit.has_blocking([_make_vuln("MEDIUM", 5.0)]) is False
    assert audit.has_blocking([_make_vuln("LOW", 2.0)]) is False


def test_no_blocking_when_empty() -> None:
    assert audit.has_blocking([]) is False


# ---------------------------------------------------------------------------
# Fail-closed policy — if we cannot determine severity, treat as HIGH.
# ---------------------------------------------------------------------------


def test_fetch_osv_severity_fails_closed_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate OSV being unreachable; the vuln must block the build."""
    import urllib.error

    def _boom(*_a: Any, **_kw: Any) -> Any:
        raise urllib.error.URLError("simulated outage")

    monkeypatch.setattr(audit.urllib.request, "urlopen", _boom)

    label, score = audit._fetch_osv_severity("GHSA-unreachable")
    assert label == "HIGH"
    assert score is None
    assert audit.has_blocking([_make_vuln(label, score)]), "unknown severity must block"


# ---------------------------------------------------------------------------
# collect_vulnerabilities — pip-audit report flattening.
# ---------------------------------------------------------------------------


def test_collect_vulnerabilities_dedups_osv_lookups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same vuln id appearing twice triggers exactly one OSV lookup."""
    calls: list[str] = []

    def _fake_fetch(vuln_id: str) -> tuple[str, float | None]:
        calls.append(vuln_id)
        return "HIGH", 7.2

    monkeypatch.setattr(audit, "_fetch_osv_severity", _fake_fetch)

    report = {
        "dependencies": [
            {
                "name": "pkg-a",
                "version": "1.0.0",
                "vulns": [{"id": "GHSA-xxx", "fix_versions": ["1.0.1"]}],
            },
            {
                "name": "pkg-b",
                "version": "2.0.0",
                "vulns": [{"id": "GHSA-xxx", "fix_versions": ["2.0.1"]}],
            },
        ]
    }
    vulns = audit.collect_vulnerabilities(report)
    assert len(vulns) == 2
    assert calls == ["GHSA-xxx"]  # one lookup, not two
    # Severity is propagated to both entries.
    assert all(v.severity_label == "HIGH" for v in vulns)


def test_format_report_empty() -> None:
    assert "no known vulnerabilities" in audit.format_report([])


def test_format_report_includes_severity_and_fix() -> None:
    text = audit.format_report([_make_vuln("CRITICAL", 9.8)])
    assert "CRITICAL" in text
    assert "1.0.1" in text  # fix version
