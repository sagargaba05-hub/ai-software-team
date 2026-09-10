from __future__ import annotations

import hashlib
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .domain import Evidence, EvidenceMode, Finding, Severity, StageResult
from .models import ModelClient
from .repository import collect_context, git_diff, is_excluded
from .skills import SkillLoader

PATCH_ROLES = {"developer", "debugger", "documentation", "refactor"}


def parse_status(text: str) -> str:
    match = re.search(
        r"(?im)^STATUS:\s*(PASS|FAIL|COMPLETE|NO_CHANGE|NOT_REQUIRED)\s*$", text
    )
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
        return StageResult(
            role,
            "FAIL",
            "Malformed or failed role output",
            metadata={"malformed": True},
        )
    findings: list[Finding] = []
    for match in re.finditer(
        r"(?ims)^Severity:\s*(BLOCKER|HIGH|MEDIUM|LOW|SUGGESTION)\s*$.*?^Finding:\s*(.+?)$.*?^(?:Evidence):\s*(.+?)$.*?^Target:\s*(architect|developer)\s*$",
        text,
    ):
        findings.append(
            Finding(
                Severity(match.group(1)),
                match.group(2).strip(),
                match.group(4).lower(),
                (match.group(3).strip(),),
            )
        )
    if role in {"reviewer", "security_reviewer"} and status == "FAIL" and not findings:
        return StageResult(
            role,
            "FAIL",
            "Review output lacks severity, evidence, or remediation owner",
            metadata={"malformed": True},
        )
    return StageResult(role, status, text.strip(), tuple(findings))


def run_command(
    repository: Path,
    command: list[str],
    *,
    timeout: int = 600,
    max_output: int = 40_000,
) -> Evidence:
    if not command or not all(isinstance(part, str) and part for part in command):
        raise ValueError("Command must be a non-empty argument list")
    started = datetime.now(UTC).isoformat()
    try:
        result = subprocess.run(
            command,
            cwd=repository,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = (result.stdout + "\n" + result.stderr).strip()[-max_output:]
        status = f"exit={result.returncode}; output={output}"
    except subprocess.TimeoutExpired:
        status = f"timeout after {timeout}s"
    return Evidence("command:" + " ".join(command), EvidenceMode.LIVE, started, status)


class AgentExecutor:
    def __init__(
        self,
        repository: Path,
        skills: SkillLoader,
        model: ModelClient,
        *,
        max_context_files: int = 30,
        max_context_chars: int = 80_000,
        allow_mutation: bool = True,
    ):
        self.repository = repository
        self.skills = skills
        self.model = model
        self.max_context_files = max_context_files
        self.max_context_chars = max_context_chars
        self.allow_mutation = allow_mutation
        self.last_stage_result: StageResult | None = None

    def run_role(
        self,
        role: str,
        objective: str,
        findings: str = "",
        *,
        run_id: str = "unbound",
        attempt: int = 1,
    ) -> str:
        started_at = datetime.now(UTC).isoformat()
        skill = self.skills.load(role, self.repository)
        context = collect_context(
            self.repository,
            self.max_context_files,
            self.max_context_chars,
            query=f"{objective}\n{findings}",
        )
        diff = (
            git_diff(self.repository)
            if role
            in {
                "refactor",
                "qa",
                "tester",
                "reviewer",
                "security_reviewer",
                "documentation",
                "release",
                "final_gate",
            }
            else ""
        )
        constraints = (
            f"\n\nProject constraints (take precedence):\n{skill.project_constraints}"
            if skill.project_constraints
            else ""
        )
        output_contract = (
            "Return a concise report with an exact STATUS line. Reviewer failures require Severity, Finding, Evidence, and Target fields. "
            "Only an authorized mutating role may include exactly one valid unified diff fence. Never include secrets or generated/vendor content."
        )
        user_prompt = f"Objective:\n{objective}\n\nExact prior findings:\n{findings or 'None'}\n\nRepository context:{context}\n\nGit diff:\n{diff}\n\n{output_contract}{constraints}"
        generate_result = getattr(self.model, "generate_result", None)
        route_metadata: dict[str, object] = {}
        if callable(generate_result):
            model_result = generate_result(
                role, skill.instructions, user_prompt, run_id=run_id
            )
            result = model_result.content
            route_metadata = {
                "requested_model": model_result.requested_model,
                "returned_model": model_result.returned_model,
                "response_id": model_result.response_id,
                "provider_attempts": model_result.attempts,
            }
        else:
            result = self.model.generate(role, skill.instructions, user_prompt)
        parsed = parse_stage_result(role, result)
        if parsed.metadata.get("malformed"):
            raise RuntimeError(parsed.summary)
        self._apply_diff_if_present(role, result)
        artifact = self._record(role, result)
        self.last_stage_result = StageResult(
            role=parsed.role,
            status=parsed.status,
            summary=parsed.summary,
            findings=parsed.findings,
            evidence=parsed.evidence,
            metadata={
                **parsed.metadata,
                "run_id": run_id,
                "attempt": attempt,
                "started_at": started_at,
                "ended_at": datetime.now(UTC).isoformat(),
                "artifact_paths": [artifact.relative_to(self.repository).as_posix()],
                "evidence_refs": [artifact.relative_to(self.repository).as_posix()],
                "route": route_metadata,
            },
        )
        return result

    def _apply_diff_if_present(self, role: str, response: str) -> None:
        fences = re.findall(r"```diff\s*(.*?)```", response, re.DOTALL)
        if len(fences) > 1:
            raise RuntimeError("Model emitted multiple patches; exactly one is allowed")
        if not fences:
            return
        raw_patch = fences[0].strip()
        if not raw_patch or raw_patch.lower() in {
            "no change",
            "no changes",
            "# no change",
            "# no changes",
        }:
            return
        if not self.allow_mutation or role not in PATCH_ROLES:
            raise RuntimeError(
                f"Role {role} is not authorized to modify repository files"
            )
        targets = self._patch_paths(raw_patch)
        for value in targets:
            relative = Path(value)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or is_excluded(self.repository / relative, self.repository)
            ):
                raise RuntimeError(
                    f"Model patch targets excluded or out-of-scope path: {value}"
                )
        patch = raw_patch + "\n"
        check = subprocess.run(
            ["git", "apply", "--check", "-"],
            cwd=self.repository,
            input=patch,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if check.returncode != 0:
            raise RuntimeError(f"Model patch failed validation: {check.stderr.strip()}")
        applied = subprocess.run(
            ["git", "apply", "-"],
            cwd=self.repository,
            input=patch,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if applied.returncode != 0:
            raise RuntimeError(f"Model patch failed to apply: {applied.stderr.strip()}")

    def _patch_paths(self, raw_patch: str) -> tuple[str, ...]:
        if "GIT binary patch" in raw_patch or re.search(
            r"(?m)^Binary files ", raw_patch
        ):
            raise RuntimeError(
                "Model patch failed validation: binary patches are not allowed"
            )
        values: list[str] = []
        saw_diff = False
        section: dict[str, bool] | None = None

        def validate_section() -> None:
            if section is None:
                return
            text_pair = section["old"] and section["new"]
            rename_pair = section["rename_from"] and section["rename_to"]
            copy_pair = section["copy_from"] and section["copy_to"]
            if not (text_pair or rename_pair or copy_pair):
                raise RuntimeError(
                    "Model patch failed validation: incomplete path headers"
                )

        for line in raw_patch.splitlines():
            if line.startswith("diff --git "):
                validate_section()
                saw_diff = True
                section = {
                    "old": False,
                    "new": False,
                    "rename_from": False,
                    "rename_to": False,
                    "copy_from": False,
                    "copy_to": False,
                }
                try:
                    fields = shlex.split(line)
                except ValueError as exc:
                    raise RuntimeError(
                        "Model patch failed validation: malformed diff header"
                    ) from exc
                if len(fields) != 4:
                    raise RuntimeError(
                        "Model patch failed validation: malformed diff header"
                    )
                values.extend(fields[2:])
            elif line.startswith("--- "):
                if section is None:
                    raise RuntimeError(
                        "Model patch failed validation: path header precedes diff header"
                    )
                section["old"] = True
                values.append(line[4:].split("\t", 1)[0].strip())
            elif line.startswith("+++ "):
                if section is None:
                    raise RuntimeError(
                        "Model patch failed validation: path header precedes diff header"
                    )
                section["new"] = True
                values.append(line[4:].split("\t", 1)[0].strip())
            else:
                metadata = re.match(r"^(rename|copy) (from|to) (.+)$", line)
                if metadata:
                    if section is None:
                        raise RuntimeError(
                            "Model patch failed validation: metadata precedes diff header"
                        )
                    section[f"{metadata.group(1)}_{metadata.group(2)}"] = True
                    values.append(metadata.group(3).strip())
        validate_section()
        if not saw_diff:
            raise RuntimeError("Model patch failed validation: incomplete path headers")
        normalized: list[str] = []
        for raw in values:
            value = raw
            if value.startswith(('"', "'")):
                try:
                    value = shlex.split(value)[0]
                except (ValueError, IndexError) as exc:
                    raise RuntimeError(
                        "Model patch failed validation: malformed quoted path"
                    ) from exc
            if value == "/dev/null":
                continue
            if value.startswith(("a/", "b/")):
                value = value[2:]
            if (
                not value
                or value in {".", ".."}
                or value.startswith(("/", "\\"))
                or re.match(r"^[A-Za-z]:[\\/]", value)
            ):
                raise RuntimeError("Model patch failed validation: empty target path")
            if value not in normalized:
                normalized.append(value)
        if not normalized:
            raise RuntimeError("Model patch failed validation: no target paths")
        return tuple(normalized)

    def _record(self, role: str, result: str) -> Path:
        mapping = {
            "qa": self.repository / ".ai-team/test-results/current.md",
            "tester": self.repository / ".ai-team/test-results/current.md",
            "reviewer": self.repository / ".ai-team/reviews/current.md",
            "security_reviewer": self.repository / ".ai-team/security/current.md",
            "release": self.repository / ".ai-team/RELEASE_REPORT.md",
            "final_gate": self.repository / ".ai-team/RELEASE_REPORT.md",
        }
        target = mapping.get(
            role, self.repository / ".ai-team/work-orders" / f"{role}-latest.md"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.rstrip() + "\n", encoding="utf-8")
        return target
