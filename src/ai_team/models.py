from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from .audit import AuditLog
from .config import Settings


class ModelClient(Protocol):
    def generate(self, role: str, system_prompt: str, user_prompt: str) -> str: ...


@dataclass(frozen=True)
class ModelResult:
    content: str
    requested_model: str
    returned_model: str
    response_id: str | None
    attempts: int


class ProviderFailure(RuntimeError):
    def __init__(self, kind: str, detail: str):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind


def find_codex_executable() -> str | None:
    explicit = os.getenv("CODEX_BINARY")
    if explicit and Path(explicit).is_file(): return explicit
    if os.name == "nt":
        extension_root = Path.home() / ".vscode" / "extensions"
        bundled = sorted(extension_root.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"), reverse=True)
        if bundled: return str(bundled[0])
        return shutil.which("codex.exe") or shutil.which("codex.cmd") or shutil.which("codex")
    return shutil.which("codex")


def _failure(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, APITimeoutError): return "TIMEOUT", True
    if isinstance(exc, APIConnectionError): return "UNAVAILABLE", True
    if isinstance(exc, APIStatusError):
        if exc.status_code in {401, 403}: return "UNAUTHORIZED", False
        if exc.status_code == 429: return "RATE_LIMIT", True
        if exc.status_code >= 500: return "UNAVAILABLE", True
        return "ROUTING_FAILURE", False
    return "MALFORMED", False


class OmniRouteModelClient:
    def __init__(self, settings: Settings, repository: Path | None = None, client: Any | None = None):
        self.settings = settings
        self.client = client or OpenAI(base_url=settings.omniroute_base_url, api_key=settings.omniroute_api_key,
                                      timeout=settings.provider_timeout_seconds, max_retries=0)
        self.audit = AuditLog(repository) if repository else None

    def generate_result(self, role: str, system_prompt: str, user_prompt: str, run_id: str = "unbound") -> ModelResult:
        route = self.settings.route_for(self.settings.capability_for(role))
        last: Exception | None = None
        for attempt in range(1, self.settings.provider_attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=route.model,
                    messages=[{"role": "system", "content": f"{self.settings.routing_marker_for(role)}\n\n{system_prompt}"},
                              {"role": "user", "content": user_prompt}], temperature=0.1,
                )
                choice = response.choices[0]
                content = choice.message.content or ""
                returned = str(getattr(response, "model", ""))
                if not content.strip(): raise ProviderFailure("EMPTY", "provider returned no content")
                expected = route.model.rsplit("/", 1)[-1].lower()
                if expected not in returned.lower():
                    raise ProviderFailure("WRONG_ROUTE", f"expected {expected}, returned {returned or 'unknown'}")
                result = ModelResult(content, route.model, returned, getattr(response, "id", None), attempt)
                self._log(run_id, role, route, "SUCCESS", attempt, returned)
                return result
            except ProviderFailure as exc:
                last = exc
                kind, retryable = exc.kind, False
            except Exception as exc:  # OpenAI client errors are normalized and sanitized.
                last = exc
                kind, retryable = _failure(exc)
            self._log(run_id, role, route, kind, attempt, "")
            if not retryable or attempt >= self.settings.provider_attempts: break
            time.sleep(min(0.25 * attempt, 1.0))
        if isinstance(last, ProviderFailure): raise last
        kind, _ = _failure(last or RuntimeError("unknown provider failure"))
        raise ProviderFailure(kind, "OmniRoute request failed; inspect safe audit metadata")

    def generate(self, role: str, system_prompt: str, user_prompt: str) -> str:
        return self.generate_result(role, system_prompt, user_prompt).content

    def _log(self, run_id: str, role: str, route: Any, result: str, attempt: int, returned: str) -> None:
        if self.audit:
            self.audit.append("usage", {"run_id": run_id, "project": str(self.audit.directory.parent.parent),
                "task": "role execution", "agent": role, "selected_model": route.model, "returned_model": returned,
                "route_type": route.route_type, "selection_reason": route.reason, "result": result,
                "attempt": attempt, "escalation": False})


@dataclass
class FakeModelClient:
    qa_failures: int = 0
    review_failures: int = 0
    calls: list[str] = field(default_factory=list)

    def generate(self, role: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(role)
        if role in {"qa", "tester"} and self.qa_failures > 0:
            self.qa_failures -= 1
            return "STATUS: FAIL\nSeverity: HIGH\nFinding: injected QA failure\nEvidence: simulated\nTarget: developer"
        if role == "reviewer" and self.review_failures > 0:
            self.review_failures -= 1
            return "STATUS: FAIL\nSeverity: HIGH\nFinding: injected review failure\nEvidence: simulated\nTarget: architect"
        if role in {"qa", "tester", "reviewer", "release", "final_gate", "security_reviewer"}:
            return f"STATUS: PASS\n{role.title()} evidence recorded by offline fake client."
        return f"STATUS: COMPLETE\n{role.title()} stage completed by offline fake client."


PREMIUM_TRIGGERS = {
    "three_local_failures", "model_disagreement", "critical_subsystems", "high_risk_security",
    "irreversible_migration", "low_confidence_high_impact", "severe_unexplained_defect",
    "incorrect_decision_cost", "senior_milestone_reasoning",
}


@dataclass(frozen=True)
class EscalationDecision:
    eligible: bool
    trigger: str
    outcome: str
    simulated: bool
    limit_position: int


class CodexEscalator:
    def __init__(self, settings: Settings, audit: AuditLog | None = None):
        self.settings = settings
        self.audit = audit

    def decide(self, trigger: str, calls_used: int, *, evidence: tuple[str, ...] = (), simulated: bool = False,
               run_id: str = "unbound") -> EscalationDecision:
        eligible = trigger in PREMIUM_TRIGGERS
        if not eligible: outcome = "INELIGIBLE"
        elif simulated: outcome = "SIMULATED_ELIGIBLE"
        elif not self.settings.codex_enabled: outcome = "DISABLED"
        elif calls_used >= self.settings.max_codex_calls_per_run: outcome = "LIMIT_REACHED"
        else: outcome = "ELIGIBLE"
        decision = EscalationDecision(eligible, trigger, outcome, simulated, calls_used + 1)
        if self.audit:
            self.audit.append("escalations", {"run_id": run_id, "trigger": trigger, "evidence_references": list(evidence),
                "local_attempts": calls_used, "enabled": self.settings.codex_enabled,
                "limit": self.settings.max_codex_calls_per_run, "limit_position": calls_used + 1,
                "selected": outcome == "ELIGIBLE", "outcome": outcome, "simulated": simulated})
        return decision

    def run(self, repository: Path, prompt: str, calls_used: int, *, trigger: str = "three_local_failures",
            simulated: bool = False, run_id: str = "unbound", reserved: bool = False) -> tuple[bool, str]:
        if not reserved:
            decision = self.decide(trigger, calls_used, simulated=simulated, run_id=run_id)
            if decision.outcome != "ELIGIBLE": return False, f"Codex escalation {decision.outcome.lower().replace('_', ' ')}."
        elif simulated or not self.settings.codex_enabled or calls_used > self.settings.max_codex_calls_per_run:
            return False, "Invalid premium reservation."
        executable = find_codex_executable()
        if not executable: return False, "Codex executable not found."
        try:
            result = subprocess.run([executable, "exec", "--full-auto", prompt], cwd=repository,
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                timeout=self.settings.codex_timeout_seconds)
        except subprocess.TimeoutExpired:
            return False, "Codex escalation timed out."
        output = (result.stdout + "\n" + result.stderr).strip()[-self.settings.codex_max_output_chars:]
        return result.returncode == 0, output
