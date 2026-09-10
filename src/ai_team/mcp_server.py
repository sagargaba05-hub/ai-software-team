from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .repository import (
    find_repository_matches,
    inspect_repository,
    read_project_context,
    read_repository_file,
    remember_project_context,
)
from .workspace_tools import github_status, run_local_program

FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
MAX_OBJECTIVE_LENGTH = 20_000

mcp = FastMCP(
    "AI Software Team",
    instructions=(
        "Use these tools to run the persistent specialist workflow. Use ai_team_status for progress, "
        "ai_team_run for a new concrete implementation objective, and ai_team_resume only "
        "after an interrupted valid run."
    ),
)


def _repository(value: str) -> Path:
    repository = Path(value).expanduser()
    if not repository.is_absolute():
        if value.strip() not in {".", "./", ".\\"}:
            raise ValueError(
                "Repository must be '.' for the current VS Code workspace or an absolute path; "
                f"other relative paths such as {value!r} are not accepted."
            )
        repository = Path.cwd()
    repository = repository.resolve()
    if not repository.is_dir():
        raise ValueError(f"Repository directory does not exist: {repository}")
    return repository


def _mcp_timeout_seconds() -> int:
    raw = os.getenv("MCP_TIMEOUT_SECONDS", "14400")
    try:
        return Settings(mcp_timeout_seconds=int(raw)).mcp_timeout_seconds
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "MCP_TIMEOUT_SECONDS must be an integer between 1 and 86400."
        ) from exc


def _execute(
    action: str, repository: Path | None = None, objective: str | None = None
) -> str:
    command = [sys.executable, "-m", "ai_team", action]
    if repository is not None:
        command.append(str(repository))
    if objective is not None:
        command.extend(["--objective", objective])
    result = subprocess.run(
        command,
        cwd=FRAMEWORK_ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_mcp_timeout_seconds(),
        check=False,
    )
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(
            output or f"ai_team {action} failed with exit code {result.returncode}"
        )
    return output or f"ai_team {action} completed with no output."


@mcp.tool()
def ai_team_doctor() -> str:
    """Check Git, Python, Ollama, OmniRoute, models, Codex, skills, and repository access."""
    return _execute("doctor")


@mcp.tool()
def ai_team_workspace() -> str:
    """Show the exact VS Code workspace bound to this global MCP process."""
    workspace = _repository(".")
    info = inspect_repository(workspace)
    result: dict[str, object] = {
        "workspace": str(info.path),
        "workspace_kind": "git_repository" if info.is_git else "directory",
        "git_repository": info.is_git,
        "branch": info.branch,
        "head": info.head,
        "origin": info.origin,
        "clean": info.clean,
        "safe_file_count": len(info.files),
        "limitations": info.limitations,
    }
    workspace_config = workspace / ".ai-workspace.json"
    if workspace_config.is_file():
        try:
            config = json.loads(workspace_config.read_text(encoding="utf-8"))
            result["workspace_kind"] = "configured_umbrella"
            result["workspace_configuration"] = {
                key: config.get(key)
                for key in (
                    "schema_version",
                    "expected_remote",
                    "git_admin_path",
                    "base_branch",
                    "worktree_root",
                )
            }
            result["next_action"] = (
                "Validate .ai-workspace.json and open the task's isolated worktree before "
                "inspecting or changing source."
            )
        except (json.JSONDecodeError, OSError) as exc:
            result["workspace_configuration_error"] = type(exc).__name__
    return json.dumps(result, indent=2)


@mcp.tool()
def ai_team_find(query: str, repository: str = ".", max_results: int = 50) -> str:
    """Find safe workspace files by path or text before claiming that a file is missing."""
    matches = find_repository_matches(_repository(repository), query, max_results)
    return json.dumps({"query": query, "matches": matches}, indent=2)


@mcp.tool()
def ai_team_read(file: str, repository: str = ".", max_chars: int = 80_000) -> str:
    """Read one UTF-8 text file inside the active workspace; secrets and generated files stay blocked."""
    return read_repository_file(_repository(repository), file, max_chars)


@mcp.tool()
def ai_team_context(repository: str = ".") -> str:
    """Show durable context explicitly recorded for the active project."""
    return read_project_context(_repository(repository))


@mcp.tool()
def ai_team_remember(note: str, repository: str = ".") -> str:
    """Persist a user-provided, non-secret project fact for future AI-team runs."""
    target = remember_project_context(_repository(repository), note)
    return f"Recorded durable project context in {target}."


@mcp.tool()
def ai_team_run_local(
    program: str,
    arguments: list[str],
    repository: str = ".",
    working_directory: str = ".",
    timeout: int = 600,
) -> str:
    """Run an allowlisted local project tool without a shell; destructive Git operations stay blocked."""
    result = run_local_program(
        _repository(repository), program, arguments, working_directory, timeout
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def ai_team_github_status(repository: str = ".") -> str:
    """Verify local Git identity, GitHub CLI authentication, and the workspace's configured origin."""
    return json.dumps(github_status(_repository(repository)), indent=2)


@mcp.tool()
def ai_team_init(repository: str = ".") -> str:
    """Create only missing project-local AI-team metadata."""
    return _execute("init", _repository(repository))


@mcp.tool()
def ai_team_status(repository: str = ".") -> str:
    """Show workflow state. Use repository='.' for the current VS Code workspace."""
    return _execute("status", _repository(repository))


@mcp.tool()
def ai_team_run(objective: str, repository: str = ".") -> str:
    """Start a full run. Use repository='.' for the current VS Code workspace."""
    objective = objective.strip()
    if not objective:
        raise ValueError("Objective must not be empty.")
    if len(objective) > MAX_OBJECTIVE_LENGTH:
        raise ValueError(f"Objective exceeds {MAX_OBJECTIVE_LENGTH} characters.")
    return _execute("run", _repository(repository), objective)


@mcp.tool()
def ai_team_resume(repository: str = ".") -> str:
    """Resume a persisted run. Use repository='.' for the current VS Code workspace."""
    return _execute("resume", _repository(repository))


@mcp.tool()
def ai_team_demo(repository: str = ".") -> str:
    """Run the bounded live/simulated controlled demonstration."""
    return _execute("demo", _repository(repository))


if __name__ == "__main__":
    mcp.run(transport="stdio")
