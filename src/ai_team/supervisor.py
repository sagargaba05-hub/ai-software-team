from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .audit import AuditLog, utc_now
from .config import Settings
from .documents import bootstrap_project
from .domain import WorkKind, WorkProfile
from .executor import AgentExecutor, finding_fingerprint, parse_status, review_target, run_command
from .models import CodexEscalator, FakeModelClient, ModelClient
from .release_gate import evaluate_release, write_release_report
from .repository import detect_project_facts, inspect_repository
from .skills import SkillLoader
from .state_store import SCHEMA_VERSION, StateStore


class WorkflowState(TypedDict, total=False):
    schema_version: int
    run_id: str
    repository: str
    objective: str
    work_kind: str
    plan: list[str]
    stage: str
    status: str
    completed: list[str]
    retry_count: int
    finding_attempts: dict[str, int]
    codex_calls: int
    premium_reservations: int
    qa_status: str
    review_status: str
    security_status: str
    documentation_status: str
    release_status: str
    findings: str
    review_target: str
    evidence: dict[str, Any]


SECURITY_TERMS = re.compile(
    r"(?i)\b(auth(?:entication|orization)?|session|account|password|encrypt|secret|credential|api|payment|personal\s+information|pii|upload|permission|database|sql|external\s+input|command|subprocess|infrastructure|dependency|network|config(?:uration)?)\b"
)
SUCCESS_STATUSES = frozenset({"PASS", "COMPLETE", "NO_CHANGE", "NOT_REQUIRED"})
WORK_STAGE_SUCCESS_STATUSES = frozenset({"PASS", "COMPLETE", "NO_CHANGE"})
ARCHITECT_REPAIR_SUCCESS_STATUSES = frozenset({"PASS", "COMPLETE"})


def classify_work(objective: str) -> WorkKind:
    text = objective.casefold()
    if re.search(r"\b(review|audit|inspect)\b", text) and not re.search(
        r"\b(fix|implement|change|build|add)\b", text
    ):
        return WorkKind.REVIEW_ONLY
    if re.search(r"\b(bug|fix|defect|regression|error|crash)\b", text):
        return WorkKind.BUGFIX
    if re.search(r"\b(refactor|rename|cleanup|restructure)\b", text):
        return WorkKind.REFACTOR
    return WorkKind.FEATURE


def security_decision(objective: str, changed_areas: tuple[str, ...] = ()) -> tuple[bool, str]:
    evidence = " ".join((objective, *changed_areas))
    matches = sorted({item.casefold() for item in SECURITY_TERMS.findall(evidence)})
    return (True, "triggered by: " + ", ".join(matches)) if matches else (False, "no security-sensitive scope detected")


def build_plan(profile: WorkProfile) -> list[str]:
    if profile.kind is WorkKind.REVIEW_ONLY:
        plan = ["inspect", "reviewer"]
    elif profile.kind is WorkKind.BUGFIX:
        plan = ["inspect", "debugger", "developer", "tester", "reviewer"]
    elif profile.kind is WorkKind.REFACTOR:
        plan = ["inspect", "developer", "tester", "reviewer"]
    else:
        plan = ["inspect", "architect", "developer", "tester", "reviewer"]
    if profile.security_required:
        plan.append("security_reviewer")
    plan += ["documentation", "final_gate"]
    return plan


def qa_route(state: WorkflowState, maximum: int) -> str:
    if state.get("qa_status") == "PASS":
        return "reviewer"
    return "developer" if state.get("retry_count", 0) < maximum else "escalation"


def reviewer_route(state: WorkflowState, maximum: int) -> str:
    if state.get("review_status") == "PASS":
        return "documentation"
    if state.get("retry_count", 0) >= maximum:
        return "escalation"
    return state.get("review_target", "developer")


def release_gate(state: WorkflowState) -> bool:
    return evaluate_release(dict(state)).status.value == "RELEASE_APPROVED"


class Supervisor:
    def __init__(self, repository: Path, settings: Settings, model: ModelClient):
        self.repository = repository.resolve()
        if not self.repository.is_dir():
            raise FileNotFoundError(f"Repository does not exist: {self.repository}")
        self.settings = settings
        self.store = StateStore(self.repository)
        self.audit = AuditLog(self.repository)
        self.model = model
        self.executor = AgentExecutor(self.repository, SkillLoader(settings.skills_root), model,
            max_context_files=settings.max_context_files, max_context_chars=settings.max_context_chars)
        self.escalator = CodexEscalator(settings, self.audit)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("workflow", self._execute)
        graph.add_edge(START, "workflow")
        graph.add_edge("workflow", END)
        return graph.compile()

    def _save(self, state: WorkflowState) -> None:
        state["updated_at"] = utc_now()  # type: ignore[typeddict-unknown-key]
        self.store.save(dict(state))

    def _role(self, state: WorkflowState, role: str, findings: str = "") -> str:
        state["stage"] = role
        self._save(state)
        try:
            result = self.executor.run_role(role, state["objective"], findings)
        except Exception as exc:
            state.update(status="BLOCKED", findings=f"{role} failed: {exc}")
            self._save(state)
            return "FAIL"
        status = parse_status(result)
        if status not in SUCCESS_STATUSES:
            state.update(status="BLOCKED", findings=result)
        else:
            completed = state.setdefault("completed", [])
            if role not in completed: completed.append(role)
        self._save(state)
        return status

    def run(self, objective: str, resume: bool = False) -> WorkflowState:
        objective = objective.strip()
        if not objective:
            raise ValueError("Objective must not be empty.")
        if resume:
            loaded = self.store.load()
            if not loaded or loaded.get("status") in {"RELEASE_APPROVED", "FAIL", "BLOCKED", "INITIALIZED"}:
                raise RuntimeError("No resumable active run is available.")
            state: WorkflowState = loaded  # type: ignore[assignment]
            state.setdefault("work_kind", classify_work(state.get("objective", objective)).value)
            state.setdefault("plan", [])
            state.setdefault("finding_attempts", {})
            state.setdefault("security_status", "NOT_REQUIRED")
            state.setdefault("requirements_status", "PASS")  # type: ignore[typeddict-unknown-key]
            state.setdefault("architecture_status", "PASS")  # type: ignore[typeddict-unknown-key]
            state.setdefault("implementation_status", "PASS")  # type: ignore[typeddict-unknown-key]
            state.setdefault("secret_hygiene_status", "PASS")  # type: ignore[typeddict-unknown-key]
            state.setdefault("scope_hygiene_status", "PASS")  # type: ignore[typeddict-unknown-key]
            state.setdefault("health_demo_status", "BLOCKED")  # type: ignore[typeddict-unknown-key]
            state.setdefault("evidence", {"run_id": state["run_id"], "mode": "SIMULATED" if isinstance(self.model, FakeModelClient) else "LIVE"})
            self.store.acquire(state["run_id"])
        else:
            prior = self.store.load()
            if prior and prior.get("status") == "RUNNING":
                raise RuntimeError("A conflicting active run already exists.")
            kind = classify_work(objective)
            required, reason = security_decision(objective)
            profile = WorkProfile(kind, required, reason)
            run_id = str(uuid.uuid4())
            state = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "repository": str(self.repository),
                "objective": objective, "work_kind": kind.value, "plan": build_plan(profile), "stage": "inspect",
                "status": "RUNNING", "completed": [], "retry_count": 0, "finding_attempts": {}, "codex_calls": 0,
                "premium_reservations": 0, "qa_status": "NOT_RUN", "review_status": "NOT_RUN",
                "security_status": "NOT_RUN" if required else "NOT_REQUIRED", "documentation_status": "NOT_RUN",
                "release_status": "NOT_RUN", "findings": "", "review_target": "developer",
                "requirements_status": "PASS", "architecture_status": "PASS", "implementation_status": "NOT_RUN",
                "secret_hygiene_status": "PASS", "scope_hygiene_status": "PASS", "health_demo_status": "BLOCKED",
                "evidence": {"run_id": run_id, "mode": "SIMULATED" if isinstance(self.model, FakeModelClient) else "LIVE"},
                "security_reason": reason}
            self.store.acquire(run_id)
            self._save(state)
        result: WorkflowState = self.graph.invoke(state, {"recursion_limit": 100})
        if result.get("status") != "RUNNING": self.store.release(result["run_id"])
        return result

    def _execute(self, state: WorkflowState) -> WorkflowState:
        bootstrap_project(self.repository)
        info = inspect_repository(self.repository)
        if "inspect" not in state["completed"]:
            state["completed"].append("inspect")
        state["repository_limitations"] = list(info.limitations)  # type: ignore[typeddict-unknown-key]
        self._save(state)
        if state.get("stage") in {"documentation", "final_gate", "release"} and "reviewer" in state.get("completed", []):
            return self._finish(state)
        kind = WorkKind(state["work_kind"])
        if kind is WorkKind.REVIEW_ONLY:
            self.executor.allow_mutation = False
            status = self._role(state, "reviewer")
            state["review_status"] = status
            state["implementation_status"] = "PASS"  # type: ignore[typeddict-unknown-key]
            return self._finish(state)
        initial = ["debugger"] if kind is WorkKind.BUGFIX else (["architect"] if kind is WorkKind.FEATURE else [])
        for role in initial:
            if role not in state["completed"] and self._role(state, role) not in WORK_STAGE_SUCCESS_STATUSES:
                return self._blocked(state)
        while True:
            if self._role(state, "developer", state.get("findings", "")) not in WORK_STAGE_SUCCESS_STATUSES:
                return self._blocked(state)
            state["implementation_status"] = "PASS"  # type: ignore[typeddict-unknown-key]
            qa = self._role(state, "tester")
            if qa == "PASS" and not isinstance(self.model, FakeModelClient):
                facts = detect_project_facts(self.repository)
                command = next(iter(facts["commands"]["test"]), None)  # type: ignore[index]
                if command == "python -m pytest":
                    evidence = run_command(self.repository, [os.sys.executable, "-m", "pytest"], timeout=600)
                    qa = "PASS" if "exit=0" in evidence.result else "FAIL"
            state["qa_status"] = qa
            self._save(state)
            if qa != "PASS":
                if not self._repair_or_escalate(state, "tester", state.get("findings", "")):
                    return self._blocked(state)
                continue
            review = self._role(state, "reviewer")
            state["review_status"] = review
            state["review_target"] = review_target(state.get("findings", ""))
            self._save(state)
            if review != "PASS":
                if not self._repair_or_escalate(state, "reviewer", state.get("findings", "")):
                    return self._blocked(state)
                if state["review_target"] == "architect" and self._role(
                    state, "architect", state.get("findings", "")
                ) not in ARCHITECT_REPAIR_SUCCESS_STATUSES:
                    return self._blocked(state)
                continue
            break
        if state["security_status"] != "NOT_REQUIRED":
            state["security_status"] = self._role(state, "security_reviewer")
            if state["security_status"] != "PASS":
                return self._blocked(state)
        return self._finish(state)

    def _repair_or_escalate(self, state: WorkflowState, source: str, finding: str) -> bool:
        fingerprint = finding_fingerprint(finding or f"{source}:unknown", source)
        attempts = state.setdefault("finding_attempts", {})
        attempts[fingerprint] = attempts.get(fingerprint, 0) + 1
        state["retry_count"] = attempts[fingerprint]
        self._save(state)
        if attempts[fingerprint] < self.settings.max_local_rework_loops:
            return True
        decision = self.escalator.decide("three_local_failures", state["codex_calls"],
            evidence=(fingerprint,), simulated=isinstance(self.model, FakeModelClient), run_id=state["run_id"])
        state["findings"] = f"Local repair exhausted after three attempts; premium decision={decision.outcome}"
        if decision.outcome != "ELIGIBLE":
            self._save(state)
            return False
        state["premium_reservations"] += 1
        state["codex_calls"] += 1
        self._save(state)  # Durable reservation is written before process invocation.
        prompt = f"Resolve finding {fingerprint} for objective {state['objective']}. Provide a bounded repair."
        ok, output = self.escalator.run(self.repository, prompt, state["codex_calls"], trigger="three_local_failures",
                                        run_id=state["run_id"], reserved=True)
        state["findings"] = output
        if not ok:
            state["open_escalation_failure"] = True  # type: ignore[typeddict-unknown-key]
        self._save(state)
        return ok

    def _finish(self, state: WorkflowState) -> WorkflowState:
        documentation = self._role(state, "documentation")
        state["documentation_status"] = "COMPLETE" if documentation in {"COMPLETE", "PASS"} else documentation
        if isinstance(self.model, FakeModelClient):
            state["health_demo_status"] = "BLOCKED"
        result = evaluate_release(dict(state))
        state["release_status"] = result.status.value
        state["status"] = result.status.value
        state["stage"] = "complete"
        write_release_report(self.repository, state["run_id"], result, limitations=state.get("repository_limitations", []))
        self._save(state)
        return state

    def _blocked(self, state: WorkflowState) -> WorkflowState:
        state["status"] = "BLOCKED"
        state["stage"] = "complete"
        self._save(state)
        return state
