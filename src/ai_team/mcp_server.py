from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP


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


def _execute(action: str, repository: Path | None = None, objective: str | None = None) -> str:
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
        timeout=14_400,
        check=False,
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode not in {0, 1}:
        raise RuntimeError(output or f"ai_team {action} failed with exit code {result.returncode}")
    return output or f"ai_team {action} completed with no output."


@mcp.tool()
def ai_team_doctor() -> str:
    """Check Git, Python, Ollama, OmniRoute, models, Codex, skills, and repository access."""
    return _execute("doctor")


@mcp.tool()
def ai_team_init(repository: str) -> str:
    """Create only missing project-local AI-team metadata."""
    return _execute("init", _repository(repository))


@mcp.tool()
def ai_team_status(repository: str) -> str:
    """Show workflow state. Use repository='.' for the current VS Code workspace."""
    return _execute("status", _repository(repository))


@mcp.tool()
def ai_team_run(objective: str, repository: str) -> str:
    """Start a full run. Use repository='.' for the current VS Code workspace."""
    objective = objective.strip()
    if not objective:
        raise ValueError("Objective must not be empty.")
    if len(objective) > MAX_OBJECTIVE_LENGTH:
        raise ValueError(f"Objective exceeds {MAX_OBJECTIVE_LENGTH} characters.")
    return _execute("run", _repository(repository), objective)


@mcp.tool()
def ai_team_resume(repository: str) -> str:
    """Resume a persisted run. Use repository='.' for the current VS Code workspace."""
    return _execute("resume", _repository(repository))


@mcp.tool()
def ai_team_demo(repository: str) -> str:
    """Run the bounded live/simulated controlled demonstration."""
    return _execute("demo", _repository(repository))


if __name__ == "__main__":
    mcp.run(transport="stdio")
