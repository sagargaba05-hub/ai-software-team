from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import TerminalState

_STAGE_FOR_CHECK = {
    "requirements": {"orchestrator"},
    "architecture": {"architect", "architecture_decision"},
    "implementation": {"developer", "debugger", "implementation_decision"},
    "tests": {"tester", "tests_decision"},
    "independent_review": {"reviewer"},
    "security": {"security_reviewer", "security_decision"},
    "documentation": {"documentation"},
}
_DETERMINISTIC_CHECKS = {
    "secret_hygiene",
    "scope_hygiene",
    "health_demo",
    "provider_failures",
    "escalation_failures",
}
_STRUCTURED_FIELDS = {
    "stage",
    "attempt",
    "started_at",
    "ended_at",
    "status",
    "artifact_paths",
    "evidence_refs",
    "findings",
    "route",
    "run_id",
}


def _stage_status_supports(expected: str, actual: str) -> bool:
    if expected == "PASS":
        return actual in {"PASS", "COMPLETE", "NO_CHANGE"}
    if expected == "COMPLETE":
        return actual in {"PASS", "COMPLETE"}
    return actual == expected


@dataclass(frozen=True)
class GateResult:
    status: TerminalState
    checks: dict[str, str]
    reasons: tuple[str, ...]


def evaluate_release(state: dict[str, Any]) -> GateResult:
    run_id = state.get("run_id")
    checks = {
        "requirements": state.get("requirements_status", "MISSING"),
        "architecture": state.get("architecture_status", "MISSING"),
        "implementation": state.get("implementation_status", "MISSING"),
        "tests": state.get("qa_status", "MISSING"),
        "independent_review": state.get("review_status", "MISSING"),
        "security": state.get("security_status", "MISSING"),
        "documentation": state.get("documentation_status", "MISSING"),
        "secret_hygiene": state.get("secret_hygiene_status", "MISSING"),
        "scope_hygiene": state.get("scope_hygiene_status", "MISSING"),
        "health_demo": state.get("health_demo_status", "MISSING"),
        "provider_failures": "FAIL" if state.get("open_provider_failures") else "PASS",
        "escalation_failures": "FAIL"
        if state.get("open_escalation_failure")
        else "PASS",
    }
    reasons: list[str] = []
    allowed = {
        "requirements": {"PASS"},
        "architecture": {"PASS", "NOT_REQUIRED"},
        "implementation": {"PASS", "NOT_REQUIRED"},
        "tests": {"PASS", "NOT_REQUIRED"},
        "independent_review": {"PASS"},
        "security": {"PASS", "NOT_REQUIRED"},
        "documentation": {"COMPLETE", "NO_CHANGE"},
        "secret_hygiene": {"PASS"},
        "scope_hygiene": {"PASS"},
        "health_demo": {"PASS"},
        "provider_failures": {"PASS"},
        "escalation_failures": {"PASS"},
    }
    if not run_id:
        reasons.append("current run_id is missing")
    evidence = state.get("evidence", {})
    if not isinstance(evidence, dict) or evidence.get("run_id") != run_id:
        reasons.append("evidence is missing or belongs to a different run")
    elif evidence.get("mode") == "SIMULATED" and checks["health_demo"] == "PASS":
        reasons.append("simulated evidence cannot satisfy live health/demo")
    for name, value in checks.items():
        if value not in allowed[name]:
            reasons.append(f"{name}={value}")
    if checks["security"] == "NOT_REQUIRED" and not state.get("security_reason"):
        reasons.append("security NOT_REQUIRED lacks a reason")
    if checks["documentation"] == "NO_CHANGE" and not state.get("documentation_reason"):
        reasons.append("documentation NO_CHANGE lacks a reason")
    stage_results = state.get("stage_results")
    current_results: list[dict[str, Any]] = []
    if not isinstance(stage_results, list):
        reasons.append("current-run structured stage evidence is missing")
    else:
        for result in stage_results:
            if not isinstance(result, dict) or not _STRUCTURED_FIELDS.issubset(result):
                continue
            if result.get("run_id") != run_id:
                continue
            current_results.append(result)
        if not current_results:
            reasons.append("current-run structured stage evidence is missing")
    for check, stages in _STAGE_FOR_CHECK.items():
        expected = checks[check]
        matching = [
            result
            for result in current_results
            if result.get("stage") in stages
            and _stage_status_supports(expected, str(result.get("status")))
        ]
        if not matching:
            reasons.append(
                f"{check} lacks matching current-run structured stage evidence"
            )
    evidence_checks = evidence.get("checks", {}) if isinstance(evidence, dict) else {}
    for check in _DETERMINISTIC_CHECKS:
        item = evidence_checks.get(check) if isinstance(evidence_checks, dict) else None
        if (
            not isinstance(item, dict)
            or item.get("run_id") != run_id
            or item.get("status") != checks[check]
            or not item.get("reference")
        ):
            reasons.append(f"{check} lacks matching current-run structured evidence")
    for finding in state.get("open_findings", []):
        if finding.get("severity") in {"BLOCKER", "HIGH"} and not finding.get(
            "resolved"
        ):
            reasons.append(f"open {finding['severity']} finding")
    blocked = any(
        "MISSING" in item
        or "missing" in item
        or "lacks matching" in item
        or "health_demo=BLOCKED" in item
        for item in reasons
    )
    status = (
        TerminalState.BLOCKED
        if blocked
        else TerminalState.FAIL
        if reasons
        else TerminalState.RELEASE_APPROVED
    )
    return GateResult(status, checks, tuple(reasons))


def write_release_report(
    repository: Path,
    run_id: str,
    result: GateResult,
    *,
    limitations: list[str] | None = None,
    evidence_references: list[str] | None = None,
    verified_commands: list[str] | None = None,
) -> Path:
    target = repository / ".ai-team" / "RELEASE_REPORT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Release Report",
        "",
        f"Run: {run_id}",
        f"Status: {result.status.value}",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: {value}" for name, value in result.checks.items())
    lines += ["", "## Reasons", ""] + (
        [f"- {reason}" for reason in result.reasons] or ["- None"]
    )
    lines += ["", "## Evidence references", ""] + (
        [f"- {item}" for item in (evidence_references or [])] or ["- None recorded"]
    )
    lines += ["", "## Verified commands", ""] + (
        [f"- `{item}`" for item in (verified_commands or [])] or ["- None recorded"]
    )
    lines += ["", "## Limitations", ""] + (
        [f"- {item}" for item in (limitations or [])] or ["- None recorded"]
    )
    lines += [
        "",
        "## Rollback",
        "",
        "Revert only the files changed by this run after preserving unrelated user work.",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
