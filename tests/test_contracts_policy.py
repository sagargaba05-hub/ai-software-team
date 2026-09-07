import json

import pytest
from pydantic import ValidationError

from ai_team.audit import AuditLog
from ai_team.config import Settings
from ai_team.domain import Capability
from ai_team.models import CodexEscalator, PREMIUM_TRIGGERS
from ai_team.provider_registry import ProviderClass, classify_provider, discover_providers
from ai_team.release_gate import evaluate_release
from ai_team.supervisor import build_plan, classify_work, security_decision
from ai_team.domain import WorkKind, WorkProfile


def test_role_and_route_decisions_are_separate():
    settings = Settings(codex_enabled=False)
    assert settings.capability_for("developer") is Capability.CODING
    assert settings.route_for(Capability.CODING).model == "ollama/qwen3-coder:30b"
    assert settings.capability_for("reviewer") is Capability.REVIEW


@pytest.mark.parametrize("field,value", [("max_local_rework_loops", 0), ("provider_attempts", 0), ("mcp_timeout_seconds", 0)])
def test_invalid_finite_bounds_fail(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})


@pytest.mark.parametrize("provider,evidence,category,eligible", [
    ("ollama-local", {}, ProviderClass.LOCAL, True),
    ("community", {"free": True, "billing_required": False}, ProviderClass.FREE, True),
    ("limited", {"free_tier": True, "no_billing": True}, ProviderClass.FREE_TIER, False),
    ("openai", {}, ProviderClass.PAID, False),
    ("mystery", {}, ProviderClass.UNKNOWN, False),
])
def test_provider_classification(provider, evidence, category, eligible):
    result = classify_provider(provider, evidence)
    assert (result.classification, result.eligible) == (category, eligible)


def test_free_tier_requires_both_evidence_and_opt_in():
    assert classify_provider("limited", {"free_tier": True, "no_billing": True}, free_tier_enabled=True).eligible
    assert not classify_provider("limited", {"free_tier": True}, free_tier_enabled=True).eligible


def test_discovery_keeps_unknown_disabled_and_detects_local():
    records = discover_providers([{"id": "ollama/qwen", "owned_by": "ollama-local"}, {"id": "x/y", "owned_by": "mystery"}])
    indexed = {item.provider: item for item in records}
    assert indexed["ollama-local"].eligible
    assert indexed["mystery"].classification is ProviderClass.UNKNOWN and not indexed["mystery"].eligible


def test_audit_redacts_and_preserves_prior_lines(tmp_path):
    audit = AuditLog(tmp_path)
    audit.append("usage", {"run_id": "one", "api_key": "do-not-write", "detail": "Bearer abc123"})
    audit.append("usage", {"run_id": "two", "result": "SUCCESS"})
    lines = (tmp_path / ".ai-team/logs/usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["api_key"] == "[REDACTED]"
    assert "abc123" not in lines[0]


@pytest.mark.parametrize("trigger", sorted(PREMIUM_TRIGGERS))
def test_each_premium_trigger_is_eligible_but_simulation_never_executes(trigger, monkeypatch):
    monkeypatch.setattr("ai_team.models.subprocess.run", lambda *a, **k: pytest.fail("subprocess invoked"))
    decision = CodexEscalator(Settings(codex_enabled=True)).decide(trigger, 0, simulated=True)
    assert decision.eligible and decision.outcome == "SIMULATED_ELIGIBLE"


def test_work_classification_security_and_plans():
    assert classify_work("Fix crash in parser") is WorkKind.BUGFIX
    assert classify_work("Refactor the cache") is WorkKind.REFACTOR
    assert classify_work("Review this module") is WorkKind.REVIEW_ONLY
    required, reason = security_decision("Change API authentication config")
    assert required and "triggered" in reason
    assert "debugger" in build_plan(WorkProfile(WorkKind.BUGFIX, False, "none"))
    assert "security_reviewer" in build_plan(WorkProfile(WorkKind.FEATURE, True, "api"))


def _passing_state():
    return {"run_id": "r", "evidence": {"run_id": "r"}, "requirements_status": "PASS",
        "architecture_status": "PASS", "implementation_status": "PASS", "qa_status": "PASS",
        "review_status": "PASS", "security_status": "NOT_REQUIRED", "documentation_status": "COMPLETE",
        "security_reason": "no security-sensitive scope detected",
        "secret_hygiene_status": "PASS", "scope_hygiene_status": "PASS", "health_demo_status": "PASS",
        "open_provider_failures": False, "open_escalation_failure": False, "open_findings": []}


@pytest.mark.parametrize("key", ["requirements_status", "architecture_status", "implementation_status", "qa_status",
    "review_status", "security_status", "documentation_status", "secret_hygiene_status", "scope_hygiene_status", "health_demo_status"])
def test_release_gate_has_negative_case_for_every_required_check(key):
    state = _passing_state(); state[key] = "FAIL"
    assert evaluate_release(state).status.value != "RELEASE_APPROVED"


def test_release_gate_rejects_stale_evidence_and_open_high():
    state = _passing_state(); state["evidence"] = {"run_id": "old"}
    assert evaluate_release(state).status.value != "RELEASE_APPROVED"
    state = _passing_state(); state["open_findings"] = [{"severity": "HIGH", "resolved": False}]
    assert evaluate_release(state).status.value == "FAIL"
