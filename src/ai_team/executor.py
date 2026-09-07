from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .domain import Evidence, EvidenceMode, Finding, Severity, StageResult
from .models import ModelClient
from .repository import collect_context, git_diff, is_excluded
from .skills import SkillLoader

PATCH_ROLES = {"developer", "debugger", "documentation", "refactor"}


def parse_status(text: str) -> str:
    match = re.search(r"(?im)^STATUS:\s*(PASS|FAIL|COMPLETE|NO_CHANGE|NOT_REQUIRED)\s*$", text)
    return match.group(1).upper() if match else "FAIL"


def review_target(text: str) -> str:
    match = re.search(r"(?im)^Target:\s*(architect|developer)\b", text)
    return match.group(1).lower() if match else "developer"


def finding_fingerprint(text: str, source: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().casefold())
    return hashlib.sha256(f"{source}:{normalized}".encode()).hexdigest()[:20]


def parse_stage_result(role: str, text: str) -> StageResult:
    status = parse_status(text)
    if status == "FAIL" and not re.search(r"(?im)^(Finding|Actual|Error):\s*\S", text):
        return StageResult(role, "FAIL", "Malformed or failed role output", metadata={"malformed": True})
    findings: list[Finding] = []
    for match in re.finditer(r"(?ims)^Severity:\s*(BLOCKER|HIGH|MEDIUM|LOW|SUGGESTION)\s*$.*?^Finding:\s*(.+?)$.*?^(?:Evidence):\s*(.+?)$.*?^Target:\s*(architect|developer)\s*$", text):
        findings.append(Finding(Severity(match.group(1)), match.group(2).strip(), match.group(4).lower(), (match.group(3).strip(),)))
    if role in {"reviewer", "security_reviewer"} and status == "FAIL" and not findings:
        return StageResult(role, "FAIL", "Review output lacks severity, evidence, or remediation owner", metadata={"malformed": True})
    return StageResult(role, status, text.strip(), tuple(findings))


def run_command(repository: Path, command: list[str], *, timeout: int = 600, max_output: int = 40_000) -> Evidence:
    if not command or not all(isinstance(part, str) and part for part in command):
        raise ValueError("Command must be a non-empty argument list")
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = subprocess.run(command, cwd=repository, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout, check=False)
        output = (result.stdout + "\n" + result.stderr).strip()[-max_output:]
        status = f"exit={result.returncode}; output={output}"
    except subprocess.TimeoutExpired:
        status = f"timeout after {timeout}s"
    return Evidence("command:" + " ".join(command), EvidenceMode.LIVE, started, status)


class AgentExecutor:
    def __init__(self, repository: Path, skills: SkillLoader, model: ModelClient, *, max_context_files: int = 30,
                 max_context_chars: int = 80_000, allow_mutation: bool = True):
        self.repository = repository
        self.skills = skills
        self.model = model
        self.max_context_files = max_context_files
        self.max_context_chars = max_context_chars
        self.allow_mutation = allow_mutation

    def run_role(self, role: str, objective: str, findings: str = "") -> str:
        skill = self.skills.load(role, self.repository)
        context = collect_context(self.repository, self.max_context_files, self.max_context_chars)
        diff = git_diff(self.repository) if role in {"refactor", "qa", "tester", "reviewer", "security_reviewer", "documentation", "release", "final_gate"} else ""
        constraints = f"\n\nProject constraints (take precedence):\n{skill.project_constraints}" if skill.project_constraints else ""
        output_contract = ("Return a concise report with an exact STATUS line. Reviewer failures require Severity, Finding, Evidence, and Target fields. "
                           "Only an authorized mutating role may include exactly one valid unified diff fence. Never include secrets or generated/vendor content.")
        user_prompt = f"Objective:\n{objective}\n\nExact prior findings:\n{findings or 'None'}\n\nRepository context:{context}\n\nGit diff:\n{diff}\n\n{output_contract}{constraints}"
        result = self.model.generate(role, skill.instructions, user_prompt)
        parsed = parse_stage_result(role, result)
        if parsed.metadata.get("malformed"):
            raise RuntimeError(parsed.summary)
        self._apply_diff_if_present(role, result)
        self._record(role, result)
        return result

    def _apply_diff_if_present(self, role: str, response: str) -> None:
        fences = re.findall(r"```diff\s*(.*?)```", response, re.DOTALL)
        if len(fences) > 1: raise RuntimeError("Model emitted multiple patches; exactly one is allowed")
        if not fences: return
        raw_patch = fences[0].strip()
        if not raw_patch or raw_patch.lower() in {"no change", "no changes", "# no change", "# no changes"}: return
        if not self.allow_mutation or role not in PATCH_ROLES:
            raise RuntimeError(f"Role {role} is not authorized to modify repository files")
        targets = re.findall(r"(?m)^\+\+\+\s+(?:b/)?(.+)$", raw_patch)
        if not targets: raise RuntimeError("Model patch failed validation: no target paths")
        for value in targets:
            if value == "/dev/null": continue
            relative = Path(value.strip())
            if relative.is_absolute() or ".." in relative.parts or is_excluded(self.repository / relative, self.repository):
                raise RuntimeError(f"Model patch targets excluded or out-of-scope path: {value}")
        patch = raw_patch + "\n"
        check = subprocess.run(["git", "apply", "--check", "-"], cwd=self.repository, input=patch, text=True,
                               encoding="utf-8", errors="replace", capture_output=True, check=False)
        if check.returncode != 0: raise RuntimeError(f"Model patch failed validation: {check.stderr.strip()}")
        applied = subprocess.run(["git", "apply", "-"], cwd=self.repository, input=patch, text=True,
                                 encoding="utf-8", errors="replace", capture_output=True, check=False)
        if applied.returncode != 0: raise RuntimeError(f"Model patch failed to apply: {applied.stderr.strip()}")

    def _record(self, role: str, result: str) -> None:
        mapping = {"qa": self.repository / ".ai-team/test-results/current.md", "tester": self.repository / ".ai-team/test-results/current.md",
                   "reviewer": self.repository / ".ai-team/reviews/current.md", "security_reviewer": self.repository / ".ai-team/security/current.md",
                   "release": self.repository / ".ai-team/RELEASE_REPORT.md", "final_gate": self.repository / ".ai-team/RELEASE_REPORT.md"}
        target = mapping.get(role, self.repository / ".ai-team/work-orders" / f"{role}-latest.md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.rstrip() + "\n", encoding="utf-8")
