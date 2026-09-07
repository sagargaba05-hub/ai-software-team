from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import TerminalState


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
        "escalation_failures": "FAIL" if state.get("open_escalation_failure") else "PASS",
    }
    reasons: list[str] = []
    allowed = {
        "requirements": {"PASS"}, "architecture": {"PASS"}, "implementation": {"PASS"},
        "tests": {"PASS"}, "independent_review": {"PASS"},
        "security": {"PASS", "NOT_REQUIRED"}, "documentation": {"COMPLETE", "NO_CHANGE"},
        "secret_hygiene": {"PASS"}, "scope_hygiene": {"PASS"}, "health_demo": {"PASS"},
        "provider_failures": {"PASS"}, "escalation_failures": {"PASS"},
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
    for finding in state.get("open_findings", []):
        if finding.get("severity") in {"BLOCKER", "HIGH"} and not finding.get("resolved"):
            reasons.append(f"open {finding['severity']} finding")
    blocked = any("MISSING" in item or "health_demo=BLOCKED" in item for item in reasons)
    status = TerminalState.BLOCKED if blocked else TerminalState.FAIL if reasons else TerminalState.RELEASE_APPROVED
    return GateResult(status, checks, tuple(reasons))


def write_release_report(repository: Path, run_id: str, result: GateResult, *, limitations: list[str] | None = None) -> Path:
    target = repository / ".ai-team" / "RELEASE_REPORT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Release Report", "", f"Run: {run_id}", f"Status: {result.status.value}", "", "## Checks", ""]
    lines.extend(f"- {name}: {value}" for name, value in result.checks.items())
    lines += ["", "## Reasons", ""] + ([f"- {reason}" for reason in result.reasons] or ["- None"])
    lines += ["", "## Limitations", ""] + ([f"- {item}" for item in (limitations or [])] or ["- None recorded"])
    lines += ["", "## Rollback", "", "Revert only the files changed by this run after preserving unrelated user work.", ""]
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
