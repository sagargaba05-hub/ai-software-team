from pathlib import Path

from ai_team.config import Settings
from ai_team.models import CodexEscalator, FakeModelClient
from ai_team.state_store import StateStore
from ai_team.supervisor import Supervisor, qa_route, release_gate, reviewer_route


def _add_structured_evidence(state):
    run_id = state["run_id"]
    stages = {
        "orchestrator": "PASS",
        "architect": "PASS",
        "developer": "PASS",
        "tester": "PASS",
        "reviewer": "PASS",
        "security_decision": "NOT_REQUIRED",
        "documentation": "COMPLETE",
    }
    state["stage_results"] = [
        {
            "run_id": run_id,
            "stage": stage,
            "attempt": 1,
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": "2026-01-01T00:00:01+00:00",
            "status": status,
            "artifact_paths": [],
            "evidence_refs": [f"test:{stage}"],
            "findings": [],
            "route": {},
        }
        for stage, status in stages.items()
    ]
    state["evidence"]["checks"] = {
        name: {"run_id": run_id, "status": status, "reference": f"test:{name}"}
        for name, status in {
            "secret_hygiene": "PASS",
            "scope_hygiene": "PASS",
            "health_demo": "PASS",
            "provider_failures": "PASS",
            "escalation_failures": "PASS",
        }.items()
    }


def settings(skills_root: Path, **updates) -> Settings:
    return Settings(skills_root=skills_root, codex_enabled=False, **updates)


def test_role_routing_by_capability(skills_root):
    config = settings(skills_root)
    assert config.model_for("developer") == "ollama/qwen3-coder:30b"
    assert config.model_for("reviewer") == "ollama/gpt-oss:20b"
    assert config.model_for("product") == "ollama/gpt-oss:20b"
    assert config.routing_marker_for("developer") == "AI_TEAM_ROUTE_CODING"
    assert config.routing_marker_for("qa") == "AI_TEAM_ROUTE_CODING"
    assert config.routing_marker_for("reviewer") == "AI_TEAM_ROUTE_REASONING"
    assert config.routing_marker_for("release") == "AI_TEAM_ROUTE_REASONING"


def test_qa_failure_routes_to_developer_then_exhausts():
    assert qa_route({"qa_status": "FAIL", "retry_count": 1}, 3) == "developer"
    assert qa_route({"qa_status": "FAIL", "retry_count": 4}, 3) == "escalation"
    assert qa_route({"qa_status": "PASS"}, 3) == "reviewer"


def test_review_failure_routes_to_correct_role():
    assert (
        reviewer_route(
            {"review_status": "FAIL", "review_target": "architect", "retry_count": 1}, 3
        )
        == "architect"
    )
    assert (
        reviewer_route(
            {"review_status": "FAIL", "review_target": "developer", "retry_count": 1}, 3
        )
        == "developer"
    )


def test_release_gate_requires_all_three_gates():
    base = {
        "run_id": "run-1",
        "evidence": {"run_id": "run-1"},
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
    }
    _add_structured_evidence(base)
    assert release_gate(base)
    for key in (
        "requirements_status",
        "architecture_status",
        "implementation_status",
        "qa_status",
        "review_status",
        "security_status",
        "documentation_status",
        "secret_hygiene_status",
        "scope_hygiene_status",
        "health_demo_status",
    ):
        broken = dict(base)
        broken[key] = "FAIL"
        assert not release_gate(broken)


def test_codex_escalation_limit_without_invocation(tmp_path, skills_root):
    config = settings(skills_root, max_codex_calls_per_run=0)
    ok, message = CodexEscalator(config).run(tmp_path, "test", 0)
    assert not ok
    assert "disabled" in message.lower() or "limit" in message.lower()


def test_complete_graph_retries_qa_and_review(tmp_path, skills_root):
    model = FakeModelClient(qa_failures=1, review_failures=1)
    result = Supervisor(tmp_path, settings(skills_root), model).run(
        "Offline workflow test"
    )
    assert result["status"] == "BLOCKED"
    assert model.calls.count("tester") == 3
    assert model.calls.count("reviewer") == 2
    assert (tmp_path / ".ai-team" / "RELEASE_REPORT.md").exists()
    assert '"status": "BLOCKED"' in (tmp_path / ".ai-team" / "state.json").read_text(
        encoding="utf-8"
    )


def test_exactly_three_failed_checks_stop_without_fourth_or_codex(
    tmp_path, skills_root
):
    model = FakeModelClient(qa_failures=4)
    result = Supervisor(tmp_path, settings(skills_root), model).run(
        "Build a local parser"
    )
    assert result["status"] == "BLOCKED"
    assert model.calls.count("tester") == 4
    assert model.calls.count("developer") == 4
    assert result["codex_calls"] == 0
    assert "three repair-and-recheck cycles" in result["findings"]


def test_required_stage_failure_stops_immediately(tmp_path, skills_root):
    class FailingDeveloper(FakeModelClient):
        def generate(self, role, system_prompt, user_prompt):
            self.calls.append(role)
            return (
                "STATUS: FAIL\nError: implementation failed"
                if role == "developer"
                else super().generate(role, system_prompt, user_prompt)
            )

    model = FailingDeveloper()
    result = Supervisor(tmp_path, settings(skills_root), model).run("Build a parser")
    assert result["status"] == "BLOCKED"
    assert "tester" not in model.calls


def test_resume_from_persisted_stage(tmp_path, skills_root):
    config = settings(skills_root)
    supervisor = Supervisor(tmp_path, config, FakeModelClient())
    supervisor.store.save(
        {
            "repository": str(tmp_path),
            "objective": "Resume test",
            "stage": "documentation",
            "status": "RUNNING",
            "completed": ["qa", "reviewer"],
            "retry_count": 0,
            "codex_calls": 0,
            "qa_status": "PASS",
            "review_status": "PASS",
            "documentation_status": "NOT_RUN",
            "release_status": "NOT_RUN",
            "findings": "",
        }
    )
    result = supervisor.run("ignored", resume=True)
    assert result["status"] == "BLOCKED"
    assert StateStore(tmp_path).load()["stage"] == "complete"
