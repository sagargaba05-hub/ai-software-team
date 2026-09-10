from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .repository import inspect_repository, is_excluded

ALLOWED_PROGRAMS = frozenset(
    {
        "git",
        "git.exe",
        "node",
        "node.exe",
        "npm",
        "npm.cmd",
        "py",
        "py.exe",
        "pytest",
        "pytest.exe",
        "python",
        "python.exe",
    }
)
READ_ONLY_GIT_COMMANDS = frozenset(
    {
        "diff",
        "grep",
        "log",
        "ls-files",
        "remote",
        "rev-parse",
        "show",
        "status",
    }
)
INLINE_CODE_FLAGS = frozenset({"-c", "-e", "--eval", "--print"})


def _workspace_directory(repository: Path, value: str) -> Path:
    root = repository.resolve()
    candidate = Path(value).expanduser()
    candidate = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    if not candidate.is_relative_to(root):
        raise ValueError("Working directory must stay inside the active workspace.")
    if not candidate.is_dir():
        raise FileNotFoundError(f"Working directory does not exist: {value}")
    if candidate != root and is_excluded(candidate, root):
        raise ValueError(
            "Commands cannot run from generated, dependency, cache, or secret directories."
        )
    return candidate


def run_local_program(
    repository: Path,
    program: str,
    arguments: list[str],
    working_directory: str = ".",
    timeout: int = 600,
) -> dict[str, object]:
    if os.getenv("AI_TEAM_LOCAL_EXECUTION_ENABLED", "false").casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError(
            "Local execution is disabled by AI_TEAM_LOCAL_EXECUTION_ENABLED."
        )
    if Path(program).name != program or program.casefold() not in ALLOWED_PROGRAMS:
        raise ValueError(f"Program is not allowed: {program}")
    if not 1 <= timeout <= 1_800:
        raise ValueError("timeout must be between 1 and 1800 seconds.")
    if not isinstance(arguments, list) or not all(
        isinstance(item, str)
        and item
        and "\0" not in item
        and "\n" not in item
        and "\r" not in item
        for item in arguments
    ):
        raise ValueError("arguments must be a list of non-empty, single-line strings.")
    lowered = [item.casefold() for item in arguments]
    if any(Path(item).is_absolute() or ".." in Path(item).parts for item in arguments):
        raise ValueError("Command arguments cannot escape the active workspace.")
    if program.casefold() in {
        "python",
        "python.exe",
        "py",
        "py.exe",
        "node",
        "node.exe",
    } and any(item in INLINE_CODE_FLAGS for item in lowered):
        raise ValueError(
            "Inline code execution is not allowed; run a checked-in file or module."
        )
    program_name = program.casefold()
    cwd = _workspace_directory(repository, working_directory)
    if program_name in {"git", "git.exe"}:
        if any(
            item in {"-c", "--git-dir", "--work-tree"}
            or item.startswith(("--git-dir=", "--work-tree="))
            for item in lowered
        ):
            raise ValueError(
                "Git repository and configuration overrides are not allowed."
            )
        subcommand = next((item for item in lowered if not item.startswith("-")), "")
        if subcommand not in READ_ONLY_GIT_COMMANDS:
            raise ValueError(
                f"Git command '{subcommand or '<missing>'}' is not read-only or allowed."
            )
        if subcommand == "remote" and not (
            len(lowered) == 1
            or lowered[1:] == ["-v"]
            or (len(lowered) >= 2 and lowered[1] == "get-url")
        ):
            raise ValueError(
                "Only read-only git remote listing and get-url are allowed."
            )
    elif program_name in {"npm", "npm.cmd"}:
        if not lowered or lowered[0] not in {"test", "run", "--version", "-v"}:
            raise ValueError(
                "npm is limited to test, run <checked-in script>, and version."
            )
        if lowered[0] == "run" and len(lowered) < 2:
            raise ValueError("npm run requires a checked-in package script name.")
    elif program_name in {"python", "python.exe", "py", "py.exe"}:
        effective = (
            arguments[1:]
            if program_name in {"py", "py.exe"}
            and arguments
            and re.fullmatch(r"-\d+(?:\.\d+)?", arguments[0])
            else arguments
        )
        if effective not in (["--version"], ["-V"]):
            if effective[:2] == ["-m", "pytest"]:
                pass
            elif effective and not effective[0].startswith("-"):
                script = resolve_workspace_program_file(
                    repository, effective[0], {".py"}
                )
                effective[0] = str(script)
                arguments = arguments[: -len(effective)] + effective
            else:
                raise ValueError(
                    "Python is limited to pytest, version, or a checked-in .py file."
                )
    elif program_name in {"node", "node.exe"} and arguments not in (
        ["--version"],
        ["-v"],
    ):
        if not arguments or arguments[0].startswith("-"):
            raise ValueError(
                "Node is limited to version or a checked-in JavaScript file."
            )
        script = resolve_workspace_program_file(
            repository, arguments[0], {".js", ".cjs", ".mjs"}
        )
        arguments = [str(script), *arguments[1:]]
    executable = shutil.which(program)
    if not executable:
        raise FileNotFoundError(
            f"Executable is not installed or not on PATH: {program}"
        )
    try:
        result = subprocess.run(
            [executable, *arguments],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        return {
            "program": program,
            "arguments": arguments,
            "working_directory": str(cwd),
            "exit_code": result.returncode,
            "output": output[-40_000:],
            "truncated": len(output) > 40_000,
        }
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(
            part.decode("utf-8", "replace") if isinstance(part, bytes) else (part or "")
            for part in (exc.stdout, exc.stderr)
        ).strip()
        return {
            "program": program,
            "arguments": arguments,
            "working_directory": str(cwd),
            "exit_code": None,
            "timeout_seconds": timeout,
            "output": output[-40_000:],
            "truncated": len(output) > 40_000,
        }


def resolve_workspace_program_file(
    repository: Path, value: str, suffixes: set[str]
) -> Path:
    root = repository.resolve()
    target = (root / value).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Program file must stay inside the active workspace.")
    if not target.is_file() or target.suffix.casefold() not in suffixes:
        raise ValueError(
            "Program file must be a checked-in-style source file in the workspace."
        )
    if is_excluded(target, root):
        raise ValueError(
            "Program file cannot be in a generated, dependency, cache, or secret directory."
        )
    return target


def _github_repository_name(origin: str | None) -> str | None:
    if not origin:
        return None
    match = re.search(r"github\.com[/:]([^/]+/[^/]+)$", origin, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).removesuffix(".git")


def github_status(repository: Path) -> dict[str, object]:
    info = inspect_repository(repository)
    result: dict[str, object] = {
        "workspace": str(info.path),
        "git_repository": info.is_git,
        "branch": info.branch,
        "head": info.head,
        "clean": info.clean,
        "origin": info.origin,
        "github_authenticated": False,
        "github_account": None,
        "github_repository": None,
    }
    gh = shutil.which("gh") or shutil.which("gh.exe")
    if not gh:
        result["github_error"] = "GitHub CLI is not installed or not on PATH."
        return result
    account = subprocess.run(
        [gh, "api", "user", "--jq", ".login"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if account.returncode != 0:
        result["github_error"] = "GitHub CLI authentication check failed."
        return result
    result["github_authenticated"] = True
    result["github_account"] = account.stdout.strip() or None
    repository_name = _github_repository_name(info.origin)
    if not repository_name:
        result["github_error"] = (
            "The active workspace origin is not a GitHub repository."
        )
        return result
    remote = subprocess.run(
        [
            gh,
            "repo",
            "view",
            repository_name,
            "--json",
            "nameWithOwner,url,defaultBranchRef",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if remote.returncode != 0:
        result["github_error"] = (
            "Authenticated, but the configured GitHub repository is unavailable."
        )
        return result
    try:
        result["github_repository"] = json.loads(remote.stdout)
    except json.JSONDecodeError:
        result["github_error"] = "GitHub CLI returned malformed repository metadata."
    return result
