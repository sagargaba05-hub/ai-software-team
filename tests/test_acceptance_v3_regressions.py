from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_team import mcp_server
from ai_team.audit import AuditLog
from ai_team.config import Settings
from ai_team.executor import AgentExecutor
from ai_team.models import FakeModelClient
from ai_team.release_gate import evaluate_release
from ai_team.skills import SkillLoader
from ai_team.state_store import StateStore
from ai_team.supervisor import Supervisor


def _settings(skills_root: Path) -> Settings:
    return Settings(skills_root=skills_root, codex_enabled=False)


@pytest.mark.parametrize(
    ("pending", "completed", "expected_first"),
    [
        ("tester", ["inspect", "orchestrator", "developer"], "tester"),
        ("reviewer", ["inspect", "orchestrator", "developer", "tester"], "reviewer"),
        (
            "security_reviewer",
            ["inspect", "orchestrator", "developer", "tester", "reviewer"],
            "security_reviewer",
        ),
        (
            "documentation",
            [
                "inspect",
                "orchestrator",
                "developer",
                "tester",
                "reviewer",
                "security_reviewer",
            ],
            "documentation",
        ),
        (
            "final_gate",
            [
                "inspect",
                "orchestrator",
                "developer",
                "tester",
                "reviewer",
                "security_reviewer",
                "documentation",
            ],
            None,
        ),
    ],
)
def test_resume_cursor_starts_at_each_pending_stage(
    tmp_path, skills_root, pending, completed, expected_first
):
    model = FakeModelClient()
    supervisor = Supervisor(tmp_path, _settings(skills_root), model)
    supervisor.store.save(
        {
            "schema_version": 3,
            "run_id": f"resume-{pending}",
            "repository": str(tmp_path),
            "objective": "Refactor parser internals",
            "work_kind": "refactor",
            "plan": [
                "inspect",
                "orchestrator",
                "developer",
                "tester",
                "reviewer",
                "security_reviewer",
                "documentation",
                "final_gate",
            ],
            "stage": pending,
            "pending_stage": pending,
            "status": "RUNNING",
            "completed": completed,
            "requirements_status": "PASS",
            "architecture_status": "NOT_REQUIRED",
            "implementation_status": "PASS",
            "qa_status": "PASS" if "tester" in completed else "NOT_RUN",
            "review_status": "PASS" if "reviewer" in completed else "NOT_RUN",
            "security_status": "PASS"
            if "security_reviewer" in completed
            else "NOT_RUN",
            "security_reason": "triggered by: config",
            "documentation_status": "COMPLETE"
            if "documentation" in completed
            else "NOT_RUN",
            "release_status": "NOT_RUN",
            "retry_count": 0,
            "finding_attempts": {},
            "repair_cycles": {},
            "stage_results": [],
            "codex_calls": 0,
            "premium_reservations": 0,
            "findings": "",
        }
    )

    supervisor.run("ignored", resume=True)

    if expected_first is None:
        assert model.calls == []
    else:
        assert model.calls[0] == expected_first


class _InterruptFirstRepair(FakeModelClient):
    def generate(self, role, system_prompt, user_prompt):
        if role == "developer" and self.calls.count("developer") == 1:
            self.calls.append(role)
            raise KeyboardInterrupt("simulated interruption")
        return super().generate(role, system_prompt, user_prompt)


def test_interrupted_repair_resumes_same_cycle_without_incrementing_counter(
    tmp_path, skills_root
):
    interrupted = _InterruptFirstRepair(qa_failures=1)
    with pytest.raises(KeyboardInterrupt):
        Supervisor(tmp_path, _settings(skills_root), interrupted).run("Build a parser")
    persisted = StateStore(tmp_path).load()
    record = next(iter(persisted["repair_cycles"].values()))
    assert record["repair_started"] == 1
    assert persisted["pending_stage"] == "developer"

    resumed_model = FakeModelClient()
    Supervisor(tmp_path, _settings(skills_root), resumed_model).run(
        "ignored", resume=True
    )
    resumed = StateStore(tmp_path).load()
    record = next(iter(resumed["repair_cycles"].values()))
    assert record["repair_started"] == 1
    assert record["fresh_checks_completed"] == 1
    assert resumed_model.calls[0] == "developer"


class _PatchModel:
    def __init__(self, patch: str):
        self.patch = patch

    def generate(self, *args):
        return f"STATUS: COMPLETE\n```diff\n{self.patch}\n```\n"


@pytest.mark.parametrize(
    "patch",
    [
        """diff --git a/.env b/config.txt
similarity index 100%
rename from .env
rename to config.txt
--- a/.env
+++ b/config.txt""",
        """diff --git a/config.txt b/.env
similarity index 100%
copy from config.txt
copy to .env
--- a/config.txt
+++ b/.env""",
    ],
)
def test_patch_rename_and_copy_metadata_validate_both_sides(
    tmp_path, skills_root, patch
):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    with pytest.raises(RuntimeError, match="excluded or out-of-scope"):
        AgentExecutor(tmp_path, SkillLoader(skills_root), _PatchModel(patch)).run_role(
            "developer", "x"
        )


def test_malformed_patch_header_is_rejected_before_git_apply(tmp_path, skills_root):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    patch = """diff --git a/file.txt
--- a/file.txt
+++ b/file.txt
@@ -0,0 +1 @@
+x"""
    with pytest.raises(RuntimeError, match="malformed diff header"):
        AgentExecutor(tmp_path, SkillLoader(skills_root), _PatchModel(patch)).run_role(
            "developer", "x"
        )


def test_nested_audit_strings_redact_quoted_and_unquoted_assignments(tmp_path):
    AuditLog(tmp_path).append(
        "usage",
        {
            "run_id": "r",
            "nested": [
                "password='hunter2'",
                {
                    "detail": (
                        'authorization="Basic abc"; private_key=xyz; '
                        "authorization=Basic abc987"
                    )
                },
            ],
        },
    )
    content = (tmp_path / ".ai-team/logs/usage.jsonl").read_text(encoding="utf-8")
    assert "hunter2" not in content
    assert "Basic abc" not in content
    assert "abc987" not in content
    assert "xyz" not in content


@pytest.mark.parametrize("value", ["zero", "0", "86401", "-2"])
def test_invalid_mcp_timeout_is_rejected(monkeypatch, value):
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="MCP_TIMEOUT_SECONDS"):
        mcp_server._mcp_timeout_seconds()


def test_v2_migration_preserves_cursor_and_does_not_invent_stage_results(tmp_path):
    store = StateStore(tmp_path)
    store.save(
        {
            "schema_version": 2,
            "run_id": "legacy",
            "stage": "reviewer",
            "status": "RUNNING",
            "completed": ["developer", "tester"],
        }
    )
    state = store.load()
    assert state["schema_version"] == 3
    assert state["pending_stage"] == "reviewer"
    assert state["completed"] == ["developer", "tester"]
    assert state["stage_results"] == []


def test_stale_structured_stage_result_cannot_approve_release():
    state = {
        "run_id": "current",
        "evidence": {"run_id": "current", "mode": "LIVE", "checks": {}},
        "requirements_status": "PASS",
        "architecture_status": "PASS",
        "implementation_status": "PASS",
        "qa_status": "PASS",
        "review_status": "PASS",
        "security_status": "NOT_REQUIRED",
        "security_reason": "not required",
        "documentation_status": "COMPLETE",
        "secret_hygiene_status": "PASS",
        "scope_hygiene_status": "PASS",
        "health_demo_status": "PASS",
        "stage_results": [
            {
                "run_id": "stale",
                "stage": "tester",
                "attempt": 1,
                "started_at": "x",
                "ended_at": "y",
                "status": "PASS",
                "artifact_paths": [],
                "evidence_refs": ["old"],
                "findings": [],
                "route": {},
            }
        ],
    }
    result = evaluate_release(state)
    assert result.status.value == "BLOCKED"
    assert any(
        "current-run structured stage evidence" in reason for reason in result.reasons
    )
