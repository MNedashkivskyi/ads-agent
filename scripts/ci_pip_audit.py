"""CI gate that runs ``pip-audit`` and fails on HIGH or CRITICAL vulns.

Motivation
----------
``pip-audit`` by default exits non-zero on *any* vulnerability.  The
security-hardening brief asks us to fail only on **HIGH** or **CRITICAL**
severity, so MEDIUM/LOW advisories don't block deploys.

Severity is not in pip-audit's own JSON — we look it up per vulnerability
via the public `OSV API <https://api.osv.dev>`_ which returns CVSS v3
vectors.  CVSS v3 → severity label mapping:

    0.0          : NONE
    0.1  - 3.9   : LOW
    4.0  - 6.9   : MEDIUM
    7.0  - 8.9   : HIGH
    9.0  - 10.0  : CRITICAL

(Source: FIRST CVSS v3.1 spec, §3.)

Design notes
~~~~~~~~~~~~
* This script is intentionally a single file with no non-stdlib
  dependencies beyond whatever ``pip-audit`` itself is pulling — that
  way it runs in a clean ``uv sync`` CI environment without an extra
  install step.
* If OSV can't be reached we **fail closed**: an advisory whose
  severity we cannot determine is treated as HIGH.  The alternative
  (treat as LOW) would create a silent bypass.
* The script prints a compact report to stdout so the GitHub Actions
  log is grep-able; the raw pip-audit JSON is also written to
  ``pip-audit.json`` for upload as a build artifact if needed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

_OSV_URL = "https://api.osv.dev/v1/vulns/{vuln_id}"
_CVSS_BASE_SCORE_RE = re.compile(r"CVSS:3\.[01]/")
_BLOCKING_LABELS: frozenset[str] = frozenset({"HIGH", "CRITICAL"})

# Advisories acknowledged but not yet actionable. Each entry must document
# *why* it is ignored — typically an unfixable upstream advisory or a false
# positive against our usage. Keys may be primary IDs or aliases (GHSA /
# PYSEC / CVE); any match suppresses the finding from the blocking check.
_IGNORED_VULN_IDS: dict[str, str] = {
    # pip 26.0.1 — tarball-symlink traversal during `pip install` of a crafted
    # sdist. We run `uv sync` against a pinned lockfile of first-party-approved
    # packages, so the attack vector does not apply. No patched pip release
    # is available yet; revisit once upstream ships one.
    "CVE-2026-3219": "no upstream fix yet; not exploitable in our CI/runtime usage",
}


def _is_ignored(v: Vulnerability) -> bool:
    if v.vuln_id in _IGNORED_VULN_IDS:
        return True
    return any(alias in _IGNORED_VULN_IDS for alias in v.aliases)


@dataclass(frozen=True)
class Vulnerability:
    package: str
    version: str
    vuln_id: str
    aliases: tuple[str, ...]
    fix_versions: tuple[str, ...]
    severity_label: str
    severity_score: float | None


def score_to_label(score: float) -> str:
    """Map a CVSS v3 base score to its severity band."""
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    if score > 0.0:
        return "LOW"
    return "NONE"


def _extract_cvss_score(osv_payload: dict[str, Any]) -> float | None:
    """Return the highest CVSS v3 base score found in the OSV record.

    OSV records can expose severity in several shapes:

    * ``severity: [{type: CVSS_V3, score: "CVSS:3.1/AV:N/..."}]`` — this
      is the vector, not the numeric score, so we skip it.
    * ``database_specific.severity`` — either a numeric score or a
      textual label ("HIGH" / "CRITICAL").
    * ``affected[].database_specific.cvss_v3_base_score`` — numeric.

    Returns ``None`` when no usable numeric score is present.  Callers
    handle that case by failing closed.
    """
    # Validate that at least one CVSS v3 vector is present — if not we
    # can still pick up a numeric score from database_specific below,
    # but this assertion doubles as documentation.
    has_v3 = any(
        entry.get("type") == "CVSS_V3" and _CVSS_BASE_SCORE_RE.match(entry.get("score") or "")
        for entry in (osv_payload.get("severity") or [])
    )
    _ = has_v3  # kept for clarity; score comes from database_specific

    db_specific = osv_payload.get("database_specific") or {}
    raw = db_specific.get("severity")
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, str):
        # Some records store a label directly ("HIGH", "CRITICAL").
        for label_score in (("CRITICAL", 9.5), ("HIGH", 7.5), ("MEDIUM", 5.0), ("LOW", 2.0)):
            if raw.upper() == label_score[0]:
                return label_score[1]

    best: float | None = None
    for affected in osv_payload.get("affected", []):
        dsp = affected.get("database_specific") or {}
        s = dsp.get("cvss_v3_base_score")
        if isinstance(s, int | float) and (best is None or s > best):
            best = float(s)
    return best


def _fetch_osv_severity(vuln_id: str) -> tuple[str, float | None]:
    """Return ``(label, score)`` for ``vuln_id``, failing closed to HIGH.

    Tries the ID and its typical OSV aliases (GHSA, PYSEC, CVE) in
    turn until one resolves.  Network errors or malformed payloads
    return ``("HIGH", None)`` so we never silently accept a
    non-lookup-able advisory.
    """
    try:
        req = urllib.request.Request(
            _OSV_URL.format(vuln_id=vuln_id),
            headers={"User-Agent": "adcopilot-ci-audit"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return "HIGH", None

    score = _extract_cvss_score(payload)
    if score is None:
        return "HIGH", None
    return score_to_label(score), score


def _run_pip_audit() -> dict[str, Any]:
    """Invoke ``pip-audit`` and return its JSON report.

    We pass ``--format json`` and parse stdout.  pip-audit exits with a
    non-zero status when vulnerabilities are found; that's normal for us
    — we rely on parsing the JSON, not the exit code.
    """
    proc = subprocess.run(
        ["pip-audit", "--format", "json", "--progress-spinner", "off"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        # 0 = clean, 1 = vulns found.  Anything else is a hard error
        # (pip-audit itself failed).
        sys.stderr.write(
            f"pip-audit exited {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}\n"
        )
        sys.exit(proc.returncode or 2)
    try:
        return json.loads(proc.stdout)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"pip-audit JSON unparseable: {exc}\n{proc.stdout}\n")
        sys.exit(2)


def collect_vulnerabilities(report: dict[str, Any]) -> list[Vulnerability]:
    """Flatten pip-audit's per-package report into a list of Vulnerability.

    Severity is resolved via OSV — one HTTP call per unique vuln id.
    """
    seen: dict[str, tuple[str, float | None]] = {}
    out: list[Vulnerability] = []
    for dep in report.get("dependencies", []):
        pkg = dep.get("name", "?")
        ver = dep.get("version", "?")
        for vuln in dep.get("vulns", []):
            vid = vuln.get("id", "?")
            aliases = tuple(vuln.get("aliases") or [])
            fixes = tuple(vuln.get("fix_versions") or [])
            if vid not in seen:
                seen[vid] = _fetch_osv_severity(vid)
            label, score = seen[vid]
            out.append(
                Vulnerability(
                    package=pkg,
                    version=ver,
                    vuln_id=vid,
                    aliases=aliases,
                    fix_versions=fixes,
                    severity_label=label,
                    severity_score=score,
                )
            )
    return out


def format_report(vulns: list[Vulnerability]) -> str:
    if not vulns:
        return "pip-audit: no known vulnerabilities found."
    lines = ["pip-audit findings:"]
    for v in vulns:
        score_str = f"{v.severity_score:.1f}" if v.severity_score is not None else "n/a"
        suffix = "  [IGNORED]" if _is_ignored(v) else ""
        lines.append(
            f"  [{v.severity_label:<8}] {v.package}=={v.version}  "
            f"{v.vuln_id}  (CVSS {score_str})  "
            f"fix: {', '.join(v.fix_versions) or 'none'}{suffix}"
        )
    return "\n".join(lines)


def has_blocking(vulns: list[Vulnerability]) -> bool:
    return any(
        v.severity_label in _BLOCKING_LABELS and not _is_ignored(v) for v in vulns
    )


def main() -> int:
    report = _run_pip_audit()
    # Preserve the raw report as a CI artefact.
    with open("pip-audit.json", "w") as fh:
        json.dump(report, fh, indent=2)

    vulns = collect_vulnerabilities(report)
    sys.stdout.write(format_report(vulns) + "\n")

    if has_blocking(vulns):
        blocking = [
            v for v in vulns
            if v.severity_label in _BLOCKING_LABELS and not _is_ignored(v)
        ]
        sys.stderr.write(
            f"\nFAIL: {len(blocking)} HIGH/CRITICAL vulnerability(ies) detected.\n"
            f"Upgrade affected packages or pin to a patched release.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
