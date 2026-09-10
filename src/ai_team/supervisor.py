from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .audit import AuditLog, audit_run, utc_now
from .config import Settings
from .documents import bootstrap_project
from .domain import WorkKind, WorkProfile
from .executor import (
    AgentExecutor,
    finding_fingerprint,
    parse_status,
    review_target,
    run_command,
)
from .models import CodexEscalator, FakeModelClient, ModelClient
from .release_gate import evaluate_release, write_release_report
from .repository import changed_paths, detect_project_facts, inspect_repository
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
    pending_stage: str
    status: str
    completed: list[str]
    retry_count: int
    finding_attempts: dict[str, int]
    repair_cycles: dict[str, dict[str, Any]]
    active_repair: dict[str, Any]
    stage_results: list[dict[str, Any]]
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


def security_decision(
    objective: str, changed_areas: tuple[str, ...] = ()
) -> tuple[bool, str]:
    evidence = " ".join((objective, *changed_areas))
    matches = sorted({item.casefold() for item in SECURITY_TERMS.findall(evidence)})
    if matches:
        return True, "triggered by: " + ", ".join(matches)
    return False, "no security-sensitive scope detected"


def build_plan(profile: WorkProfile) -> list[str]:
    if profile.kind is WorkKind.REVIEW_ONLY:
        plan = ["inspect", "orchestrator", "reviewer"]
    elif profile.kind is WorkKind.BUGFIX:
        plan = [
            "inspect",
            "orchestrator",
            "debugger",
            "developer",
            "tester",
            "reviewer",
        ]
    elif profile.kind is WorkKind.REFACTOR:
        plan = ["inspect", "orchestrator", "developer", "tester", "reviewer"]
    else:
        plan = [
            "inspect",
            "orchestrator",
            "architect",
            "developer",
            "tester",
            "reviewer",
        ]
    if profile.security_required:
        plan.append("security_reviewer")
    return plan + ["documentation", "final_gate"]


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
        self.executor = AgentExecutor(
            self.repository,
            SkillLoader(settings.skills_root),
            model,
            max_context_files=settings.max_context_files,
            max_context_chars=settings.max_context_chars,
        )
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

    def _append_stage_result(
        self,
        state: WorkflowState,
        stage: str,
        status: str,
        *,
        started_at: str | None = None,
        artifact_paths: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        findings: list[dict[str, Any]] | None = None,
        route: dict[str, Any] | None = None,
        attempt: int | None = None,
    ) -> None:
        results = state.setdefault("stage_results", [])
        if attempt is None:
            attempt = 1 + sum(item.get("stage") == stage for item in results)
        results.append(
            {
                "run_id": state["run_id"],
                "stage": stage,
                "attempt": attempt,
                "started_at": started_at or utc_now(),
                "ended_at": utc_now(),
                "status": status,
                "artifact_paths": artifact_paths or [],
                "evidence_refs": evidence_refs or [],
                "findings": findings or [],
                "route": route or {},
            }
        )

    def _decision_result(
        self, state: WorkflowState, stage: str, status: str, reason: str
    ) -> None:
        existing = [
            item
            for item in state.setdefault("stage_results", [])
            if item.get("run_id") == state["run_id"] and item.get("stage") == stage
        ]
        if not existing:
            self._append_stage_result(state, stage, status, evidence_refs=[reason])
            self._save(state)

    def _role(self, state: WorkflowState, role: str, findings: str = "") -> str:
        state["stage"] = role
        state["pending_stage"] = role
        self._save(state)
        started_at = utc_now()
        attempt = 1 + sum(
            item.get("stage") == role for item in state.get("stage_results", [])
        )
        try:
            result = self.executor.run_role(
                role,
                state["objective"],
                findings,
                run_id=state["run_id"],
                attempt=attempt,
            )
            status = parse_status(result)
            parsed = self.executor.last_stage_result
            if parsed is None:
                raise RuntimeError("executor did not produce a structured stage result")
            payload = parsed.as_dict()
            metadata = payload.pop("metadata", {})
            payload["stage"] = payload.pop("role")
            payload.update(metadata)
            state.setdefault("stage_results", []).append(payload)
        except Exception as exc:  # noqa: BLE001 - provider/adapter failures become persisted evidence.
            status = "FAIL"
            result = f"{role} failed: {exc}"
            self._append_stage_result(
                state,
                role,
                status,
                started_at=started_at,
                findings=[{"summary": result}],
                attempt=attempt,
            )
        state["findings"] = "" if status in SUCCESS_STATUSES else result
        if status in SUCCESS_STATUSES:
            completed = state.setdefault("completed", [])
            if role not in completed:
                completed.append(role)
        self._save(state)
        return status

    def _ensure_defaults(self, state: WorkflowState) -> None:
        kind = classify_work(state.get("objective", ""))
        state.setdefault("work_kind", kind.value)
        required, reason = security_decision(
            state.get("objective", ""), changed_paths(self.repository)
        )
        if not state.get("plan"):
            state["plan"] = build_plan(WorkProfile(kind, required, reason))
        state.setdefault("completed", [])
        state.setdefault("finding_attempts", {})
        state.setdefault("repair_cycles", {})
        state.setdefault("stage_results", [])
        state.setdefault("pending_stage", state.get("stage", "inspect"))
        state.setdefault("security_status", "NOT_RUN" if required else "NOT_REQUIRED")
        state.setdefault("security_reason", reason)  # type: ignore[typeddict-unknown-key]
        state.setdefault("requirements_status", "NOT_RUN")  # type: ignore[typeddict-unknown-key]
        state.setdefault("architecture_status", "NOT_RUN")  # type: ignore[typeddict-unknown-key]
        state.setdefault("implementation_status", "NOT_RUN")  # type: ignore[typeddict-unknown-key]
        state.setdefault("qa_status", "NOT_RUN")
        state.setdefault("review_status", "NOT_RUN")
        state.setdefault("documentation_status", "NOT_RUN")
        state.setdefault("release_status", "NOT_RUN")
        state.setdefault("secret_hygiene_status", "PASS")  # type: ignore[typeddict-unknown-key]
        state.setdefault("scope_hygiene_status", "PASS")  # type: ignore[typeddict-unknown-key]
        state.setdefault("health_demo_status", "BLOCKED")  # type: ignore[typeddict-unknown-key]
        state.setdefault("retry_count", 0)
        state.setdefault("codex_calls", 0)
        state.setdefault("premium_reservations", 0)
        state.setdefault("findings", "")
        state.setdefault("review_target", "developer")
        state.setdefault(
            "evidence",
            {
                "run_id": state["run_id"],
                "mode": "SIMULATED"
                if isinstance(self.model, FakeModelClient)
                else "LIVE",
            },
        )

    def run(self, objective: str, resume: bool = False) -> WorkflowState:
        objective = objective.strip()
        if not objective:
            raise ValueError("Objective must not be empty.")
        if resume:
            loaded = self.store.load()
            if not loaded or loaded.get("status") in {
                "RELEASE_APPROVED",
                "FAIL",
                "BLOCKED",
                "INITIALIZED",
            }:
                raise RuntimeError("No resumable active run is available.")
            state: WorkflowState = loaded  # type: ignore[assignment]
            self._ensure_defaults(state)
            self.store.acquire(state["run_id"])
        else:
            prior = self.store.load()
            if prior and prior.get("status") == "RUNNING":
                raise RuntimeError("A conflicting active run already exists.")
            kind = classify_work(objective)
            required, reason = security_decision(objective)
            run_id = str(uuid.uuid4())
            state = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "repository": str(self.repository),
                "objective": objective,
                "work_kind": kind.value,
                "plan": build_plan(WorkProfile(kind, required, reason)),
                "stage": "inspect",
                "pending_stage": "inspect",
                "status": "RUNNING",
                "completed": [],
                "retry_count": 0,
                "finding_attempts": {},
                "repair_cycles": {},
                "stage_results": [],
                "codex_calls": 0,
                "premium_reservations": 0,
                "qa_status": "NOT_RUN",
                "review_status": "NOT_RUN",
                "security_status": "NOT_RUN" if required else "NOT_REQUIRED",
                "documentation_status": "NOT_RUN",
                "release_status": "NOT_RUN",
                "findings": "",
                "review_target": "developer",
                "requirements_status": "NOT_RUN",
                "architecture_status": "NOT_RUN",
                "implementation_status": "NOT_RUN",
                "secret_hygiene_status": "PASS",
                "scope_hygiene_status": "PASS",
                "health_demo_status": "BLOCKED",
                "evidence": {
                    "run_id": run_id,
                    "mode": "SIMULATED"
                    if isinstance(self.model, FakeModelClient)
                    else "LIVE",
                },
                "security_reason": reason,
            }
            self.store.acquire(run_id)
            self._save(state)
        with audit_run(state["run_id"]):
            result: WorkflowState = self.graph.invoke(state, {"recursion_limit": 100})
        if result.get("status") != "RUNNING":
            self.store.release(result["run_id"])
        return result

    def _cursor_index(self, state: WorkflowState) -> int:
        plan = state.get("plan", [])
        pending = state.get("pending_stage", state.get("stage", "inspect"))
        try:
            return plan.index(pending)
        except ValueError:
            return 0

    def _stage_due(self, state: WorkflowState, role: str) -> bool:
        if role in state.get("completed", []):
            return False
        plan = state.get("plan", [])
        if role not in plan:
            return False
        return plan.index(role) >= self._cursor_index(state)

    def _advance(self, state: WorkflowState, completed_stage: str) -> None:
        plan = state.get("plan", [])
        try:
            index = plan.index(completed_stage)
        except ValueError:
            return
        state["pending_stage"] = (
            plan[index + 1] if index + 1 < len(plan) else "complete"
        )
        self._save(state)

    def _recompute_security(self, state: WorkflowState) -> None:
        required, reason = security_decision(
            state["objective"], changed_paths(self.repository)
        )
        if required:
            state["security_required_latched"] = True  # type: ignore[typeddict-unknown-key]
            state["security_reason"] = reason  # type: ignore[typeddict-unknown-key]
            if state.get("security_status") == "NOT_REQUIRED":
                state["security_status"] = "NOT_RUN"
            plan = state.setdefault("plan", [])
            if "security_reviewer" not in plan:
                insertion = (
                    plan.index("documentation")
                    if "documentation" in plan
                    else len(plan)
                )
                plan.insert(insertion, "security_reviewer")
        elif not state.get("security_required_latched"):
            state["security_reason"] = reason  # type: ignore[typeddict-unknown-key]
        self._save(state)

    def _execute(self, state: WorkflowState) -> WorkflowState:
        bootstrap_project(self.repository)
        info = inspect_repository(self.repository)
        state["repository_limitations"] = list(info.limitations)  # type: ignore[typeddict-unknown-key]
        if self._stage_due(state, "inspect"):
            state["completed"].append("inspect")
            self._append_stage_result(
                state, "inspect", "PASS", evidence_refs=["repository inspection"]
            )
            self._advance(state, "inspect")

        kind = WorkKind(state["work_kind"])
        if self._stage_due(state, "orchestrator"):
            status = self._role(state, "orchestrator")
            state["requirements_status"] = (
                "PASS" if status in WORK_STAGE_SUCCESS_STATUSES else status
            )  # type: ignore[typeddict-unknown-key]
            if status not in WORK_STAGE_SUCCESS_STATUSES:
                return self._blocked(state)
            self._advance(state, "orchestrator")

        if kind is WorkKind.REVIEW_ONLY:
            state["architecture_status"] = "NOT_REQUIRED"  # type: ignore[typeddict-unknown-key]
            state["implementation_status"] = "NOT_REQUIRED"  # type: ignore[typeddict-unknown-key]
            state["qa_status"] = "NOT_REQUIRED"
            self._decision_result(
                state, "architecture_decision", "NOT_REQUIRED", "review-only work"
            )
            self._decision_result(
                state, "implementation_decision", "NOT_REQUIRED", "review-only work"
            )
            self._decision_result(
                state, "tests_decision", "NOT_REQUIRED", "review-only work"
            )
            self.executor.allow_mutation = False
            if self._stage_due(state, "reviewer"):
                state["review_status"] = self._role(state, "reviewer")
                if state["review_status"] != "PASS":
                    return self._blocked(state)
                self._advance(state, "reviewer")
            return self._security_and_finish(state)

        initial = (
            "debugger"
            if kind is WorkKind.BUGFIX
            else "architect"
            if kind is WorkKind.FEATURE
            else None
        )
        if initial and self._stage_due(state, initial):
            status = self._role(state, initial)
            if initial == "architect":
                state["architecture_status"] = (
                    "PASS" if status in WORK_STAGE_SUCCESS_STATUSES else status
                )  # type: ignore[typeddict-unknown-key]
            if status not in WORK_STAGE_SUCCESS_STATUSES:
                return self._blocked(state)
            self._advance(state, initial)
        elif kind is not WorkKind.FEATURE:
            state["architecture_status"] = "NOT_REQUIRED"  # type: ignore[typeddict-unknown-key]
            self._decision_result(
                state,
                "architecture_decision",
                "NOT_REQUIRED",
                f"{kind.value} does not require architecture",
            )

        if state.get("active_repair") and not self._repair_loop(state):
            return self._blocked(state)

        if self._stage_due(state, "developer"):
            status = self._role(state, "developer", state.get("findings", ""))
            if status not in WORK_STAGE_SUCCESS_STATUSES:
                return self._blocked(state)
            state["implementation_status"] = "PASS"  # type: ignore[typeddict-unknown-key]
            self._recompute_security(state)
            self._advance(state, "developer")

        if self._stage_due(state, "tester"):
            qa = self._run_tester(state)
            state["qa_status"] = qa
            self._save(state)
            if qa != "PASS":
                self._start_repair(state, "tester", ["developer"])
                if not self._repair_loop(state):
                    return self._blocked(state)
            self._advance(state, "tester")

        if self._stage_due(state, "reviewer"):
            review = self._role(state, "reviewer")
            state["review_status"] = review
            state["review_target"] = review_target(state.get("findings", ""))
            self._save(state)
            if review != "PASS":
                roles = [state["review_target"]]
                if roles[0] == "architect":
                    roles.append("developer")
                self._start_repair(state, "reviewer", roles)
                if not self._repair_loop(state):
                    return self._blocked(state)
            self._advance(state, "reviewer")
        return self._security_and_finish(state)

    def _run_tester(self, state: WorkflowState) -> str:
        qa = self._role(state, "tester")
        if qa == "PASS" and not isinstance(self.model, FakeModelClient):
            facts = detect_project_facts(self.repository)
            command = next(iter(facts["commands"]["test"]), None)  # type: ignore[index]
            if command == "python -m pytest":
                evidence = run_command(
                    self.repository,
                    [os.sys.executable, "-m", "pytest"],
                    timeout=600,
                )
                qa = "PASS" if "exit=0" in evidence.result else "FAIL"
                if qa == "FAIL":
                    state["findings"] = evidence.result
        return qa

    def _start_repair(
        self, state: WorkflowState, source: str, repair_roles: list[str]
    ) -> None:
        finding = state.get("findings", "") or f"{source}:unknown"
        fingerprint = finding_fingerprint(finding, source)
        cycles = state.setdefault("repair_cycles", {})
        cycles.setdefault(
            fingerprint,
            {
                "source": source,
                "finding": finding,
                "initial_failure": True,
                "repair_started": 0,
                "fresh_checks_completed": 0,
                "failed_cycles": 0,
            },
        )
        state["active_repair"] = {
            "fingerprint": fingerprint,
            "source": source,
            "repair_roles": repair_roles,
            "phase": "repair",
            "role_index": 0,
            "cycle_started": False,
        }
        state["pending_stage"] = repair_roles[0]
        self._save(state)

    def _repair_loop(self, state: WorkflowState) -> bool:
        active = state["active_repair"]
        record = state["repair_cycles"][active["fingerprint"]]
        maximum = self.settings.max_local_rework_loops
        while True:
            if record["failed_cycles"] >= maximum:
                return self._escalate_exhausted(state, active["fingerprint"])
            if active["phase"] == "repair":
                if active.get("role_index", 0) == 0 and not active.get(
                    "cycle_started", False
                ):
                    record["repair_started"] += 1
                    active["cycle_started"] = True
                    state["retry_count"] = record["repair_started"]
                    state.setdefault("finding_attempts", {})[active["fingerprint"]] = (
                        record["repair_started"]
                    )
                    self._save(state)
                roles = active["repair_roles"]
                while active["role_index"] < len(roles):
                    role = roles[active["role_index"]]
                    state["pending_stage"] = role
                    self._save(state)
                    status = self._role(state, role, record["finding"])
                    expected = (
                        ARCHITECT_REPAIR_SUCCESS_STATUSES
                        if role == "architect"
                        else WORK_STAGE_SUCCESS_STATUSES
                    )
                    if status not in expected:
                        return False
                    if role == "developer":
                        state["implementation_status"] = "PASS"  # type: ignore[typeddict-unknown-key]
                        self._recompute_security(state)
                    active["role_index"] += 1
                    self._save(state)
                active["phase"] = "recheck"
                state["pending_stage"] = active["source"]
                self._save(state)

            source = active["source"]
            if source == "tester":
                status = self._run_tester(state)
            else:
                qa = self._run_tester(state)
                state["qa_status"] = qa
                if qa != "PASS":
                    state["findings"] = (
                        "Reviewer repair failed fresh tester check: "
                        + state.get("findings", "")
                    )
                    status = "FAIL"
                else:
                    status = self._role(state, "reviewer")
            record["fresh_checks_completed"] += 1
            if source == "tester":
                state["qa_status"] = status
            else:
                state["review_status"] = status
            if status == "PASS":
                state.pop("active_repair", None)
                state["findings"] = ""
                self._save(state)
                return True
            record["failed_cycles"] += 1
            record["finding"] = state.get("findings", record["finding"])
            active["phase"] = "repair"
            active["role_index"] = 0
            active["cycle_started"] = False
            self._save(state)

    def _escalate_exhausted(self, state: WorkflowState, fingerprint: str) -> bool:
        decision = self.escalator.decide(
            "three_local_failures",
            state["codex_calls"],
            evidence=(fingerprint,),
            simulated=isinstance(self.model, FakeModelClient),
            run_id=state["run_id"],
        )
        state["findings"] = (
            "Local repair exhausted after three repair-and-recheck cycles; "
            f"premium decision={decision.outcome}"
        )
        if decision.outcome != "ELIGIBLE":
            self._save(state)
            return False
        state["premium_reservations"] += 1
        state["codex_calls"] += 1
        self._save(state)
        prompt = f"Resolve finding {fingerprint} for objective {state['objective']}. Provide a bounded repair."
        ok, output = self.escalator.run(
            self.repository,
            prompt,
            state["codex_calls"],
            trigger="three_local_failures",
            run_id=state["run_id"],
            reserved=True,
        )
        state["findings"] = output
        if not ok:
            state["open_escalation_failure"] = True  # type: ignore[typeddict-unknown-key]
        self._save(state)
        return ok

    def _security_and_finish(self, state: WorkflowState) -> WorkflowState:
        self._recompute_security(state)
        if state["security_status"] != "NOT_REQUIRED":
            if self._stage_due(state, "security_reviewer"):
                state["security_status"] = self._role(state, "security_reviewer")
                if state["security_status"] != "PASS":
                    return self._blocked(state)
                self._advance(state, "security_reviewer")
        else:
            self._decision_result(
                state,
                "security_decision",
                "NOT_REQUIRED",
                str(
                    state.get("security_reason", "no security-sensitive scope detected")
                ),
            )
        return self._finish(state)

    def _record_deterministic_evidence(self, state: WorkflowState) -> None:
        evidence = state.setdefault("evidence", {})
        evidence["run_id"] = state["run_id"]
        checks = evidence.setdefault("checks", {})
        values = {
            "secret_hygiene": state.get("secret_hygiene_status", "MISSING"),
            "scope_hygiene": state.get("scope_hygiene_status", "MISSING"),
            "health_demo": state.get("health_demo_status", "MISSING"),
            "provider_failures": "FAIL"
            if state.get("open_provider_failures")
            else "PASS",
            "escalation_failures": "FAIL"
            if state.get("open_escalation_failure")
            else "PASS",
        }
        for name, status in values.items():
            checks[name] = {
                "run_id": state["run_id"],
                "status": status,
                "reference": f"state:{name}",
                "timestamp": utc_now(),
            }

    def _finish(self, state: WorkflowState) -> WorkflowState:
        if self._stage_due(state, "documentation"):
            documentation = self._role(state, "documentation")
            state["documentation_status"] = (
                "COMPLETE" if documentation in {"COMPLETE", "PASS"} else documentation
            )
            if documentation not in {"COMPLETE", "PASS", "NO_CHANGE"}:
                return self._blocked(state)
            self._advance(state, "documentation")
        self._record_deterministic_evidence(state)
        result = evaluate_release(dict(state))
        state["release_status"] = result.status.value
        state["status"] = result.status.value
        state["stage"] = "final_gate"
        state["pending_stage"] = "complete"
        self._append_stage_result(
            state,
            "final_gate",
            result.status.value,
            artifact_paths=[".ai-team/RELEASE_REPORT.md"],
            evidence_refs=list(result.reasons)
            or ["all deterministic release checks passed"],
        )
        if "final_gate" not in state.setdefault("completed", []):
            state["completed"].append("final_gate")
        write_release_report(
            self.repository,
            state["run_id"],
            result,
            limitations=state.get("repository_limitations", []),
            evidence_references=sorted(
                {
                    reference
                    for item in state.get("stage_results", [])
                    for reference in item.get("evidence_refs", [])
                }
            ),
        )
        state["stage"] = "complete"
        self._save(state)
        return state

    def _blocked(self, state: WorkflowState) -> WorkflowState:
        state["status"] = "BLOCKED"
        state["stage"] = "complete"
        self._save(state)
        return state
