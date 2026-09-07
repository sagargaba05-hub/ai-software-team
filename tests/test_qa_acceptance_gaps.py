from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_team.audit import AuditLog
from ai_team.config import Settings
from ai_team.documents import bootstrap_project
from ai_team.models import FakeModelClient
from ai_team.release_gate import evaluate_release
from ai_team.state_store import StateStore
from ai_team.supervisor import Supervisor
from ai_team import mcp_server


def _settings(skills_root: Path, **updates) -> Settings:
    return Settings(skills_root=skills_root, codex_enabled=False, **updates)


def test_bootstrap_is_idempotent_on_windows_space_and_unicode_path(tmp_path):
    repository = tmp_path / "client repo — café"
    repository.mkdir()
    readme = repository / "README.md"
    original = b"existing readme with odd byte: \x96\n"
    readme.write_bytes(original)

    first = bootstrap_project(repository)
    second = bootstrap_project(repository)

    assert first
    assert second == []
    assert readme.read_bytes() == original


def test_three_failed_repairs_are_allowed_before_escalation(tmp_path, skills_root):
    """R-06 counts a cycle only after a repair and fresh check, not the initial QA finding."""
    model = FakeModelClient(qa_failures=4)
    result = Supervisor(tmp_path, _settings(skills_root), model).run("Build a local parser")

    assert result["status"] == "BLOCKED"
    assert model.calls.count("developer") == 4  # initial implementation plus three repairs
    assert model.calls.count("tester") == 4  # initial finding plus a fresh check per repair
    assert model.qa_failures == 0


def test_resume_does_not_rerun_a_completed_developer_stage(tmp_path, skills_root):
    model = FakeModelClient()
    supervisor = Supervisor(tmp_path, _settings(skills_root), model)
    supervisor.store.save(
        {
            "schema_version": 2,
            "run_id": "resume-run",
            "repository": str(tmp_path),
            "objective": "Refactor the parser",
            "work_kind": "refactor",
            "plan": ["inspect", "developer", "tester", "reviewer", "documentation", "final_gate"],
            "stage": "tester",
            "status": "RUNNING",
            "completed": ["inspect", "developer"],
            "retry_count": 0,
            "finding_attempts": {},
            "codex_calls": 0,
            "premium_reservations": 0,
            "qa_status": "NOT_RUN",
            "review_status": "NOT_RUN",
            "security_status": "NOT_REQUIRED",
            "security_reason": "no security-sensitive scope detected",
            "documentation_status": "NOT_RUN",
            "release_status": "NOT_RUN",
            "findings": "",
        }
    )

    supervisor.run("ignored", resume=True)

    assert "developer" not in model.calls
    assert model.calls[0] == "tester"


def test_selected_final_gate_stage_is_recorded_as_completed(tmp_path, skills_root):
    model = FakeModelClient()
    result = Supervisor(tmp_path, _settings(skills_root), model).run("Build a local parser")

    assert "final_gate" in result["completed"]


class _SecurityChangingModel(FakeModelClient):
    def __init__(self):
        super().__init__()
        self.changed = False

    def generate(self, role, system_prompt, user_prompt):
        self.calls.append(role)
        if role == "developer" and not self.changed:
            self.changed = True
            return """STATUS: COMPLETE
```diff
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1 +1 @@
-MODE = "old"
+MODE = "new"
```
"""
        if role in {"tester", "reviewer", "security_reviewer", "final_gate"}:
            return "STATUS: PASS\nEvidence: controlled test"
        return f"STATUS: COMPLETE\n{role} complete"


def test_security_trigger_is_recomputed_from_changed_areas(tmp_path, skills_root):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text('MODE = "old"\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src/auth.py"], check=True, capture_output=True)
    model = _SecurityChangingModel()

    Supervisor(tmp_path, _settings(skills_root), model).run("Improve module behavior")

    assert "security_reviewer" in model.calls


def test_audit_redacts_secret_values_embedded_in_strings(tmp_path):
    AuditLog(tmp_path).append(
        "usage",
        {"run_id": "r", "result": "password=hunter2 token=abc123 api_key=live-secret"},
    )
    line = (tmp_path / ".ai-team" / "logs" / "usage.jsonl").read_text(encoding="utf-8")

    assert "hunter2" not in line
    assert "abc123" not in line
    assert "live-secret" not in line


class _SecretDeletionPatch:
    def generate(self, *args):
        return """STATUS: COMPLETE
```diff
diff --git a/.env b/.env
deleted file mode 100644
--- a/.env
+++ /dev/null
@@ -1 +0,0 @@
-TOKEN=x
```
"""


def test_patch_cannot_delete_an_excluded_secret_file(tmp_path, skills_root):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".env"], check=True, capture_output=True)

    from ai_team.executor import AgentExecutor
    from ai_team.skills import SkillLoader

    with pytest.raises(RuntimeError, match="excluded or out-of-scope"):
        AgentExecutor(tmp_path, SkillLoader(skills_root), _SecretDeletionPatch()).run_role("developer", "x")
    assert secret.read_text(encoding="utf-8") == "TOKEN=x\n"


def test_mcp_timeout_uses_configured_bound(monkeypatch, tmp_path):
    captured = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return Result()

    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "7")
    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)
    mcp_server._execute("status", tmp_path)

    assert captured["timeout"] == 7


def test_release_gate_requires_structured_stage_evidence():
    state = {
        "run_id": "r",
        "evidence": {"run_id": "r", "mode": "LIVE"},
        "requirements_status": "PASS",
        "architecture_status": "PASS",
        "implementation_status": "PASS",
        "qa_status": "PASS",
        "review_status": "PASS",
        "security_status": "NOT_REQUIRED",
        "security_reason": "no security-sensitive scope detected",
        "documentation_status": "COMPLETE",
        "secret_hygiene_status": "PASS",
        "scope_hygiene_status": "PASS",
        "health_demo_status": "PASS",
        "open_provider_failures": False,
        "open_escalation_failure": False,
        "open_findings": [],
    }

    assert evaluate_release(state).status.value == "BLOCKED"


class _AuditedPassingModel(FakeModelClient):
    def __init__(self, repository: Path):
        super().__init__()
        self.audit = AuditLog(repository)

    def generate(self, role, system_prompt, user_prompt):
        self.audit.append(
            "usage",
            {
                "run_id": "unbound",
                "project": "test",
                "task": "role execution",
                "agent": role,
                "selected_model": "local",
                "route_type": "LOCAL",
                "selection_reason": "test",
                "result": "SUCCESS",
                "escalation": False,
            },
        )
        return super().generate(role, system_prompt, user_prompt)


def test_normal_run_model_activity_is_attributed_to_current_run(tmp_path, skills_root):
    model = _AuditedPassingModel(tmp_path)
    result = Supervisor(tmp_path, _settings(skills_root), model).run("Build a local parser")
    records = [
        json.loads(line)
        for line in (tmp_path / ".ai-team" / "logs" / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert records
    assert {record["run_id"] for record in records} == {result["run_id"]}
