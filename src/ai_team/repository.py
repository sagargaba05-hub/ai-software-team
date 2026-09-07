from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .constants import BINARY_SUFFIXES, EXCLUDED_DIRS, SENSITIVE_FILENAMES, SENSITIVE_SUFFIXES


@dataclass(frozen=True)
class RepositoryInfo:
    path: Path
    is_git: bool
    files: tuple[Path, ...]
    head: str | None = None
    origin: str | None = None
    branch: str | None = None
    clean: bool | None = None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeScope:
    staged: str
    unstaged: str
    untracked: tuple[Path, ...]


def is_excluded(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    parts = tuple(part.casefold() for part in relative.parts)
    excluded = {item.casefold() for item in EXCLUDED_DIRS}
    if any(part in excluded for part in parts):
        return True
    if len(parts) >= 2 and parts[0] == ".ai-team" and parts[1] in {"runtime", "logs"}:
        return True
    name = path.name.casefold()
    return (path.suffix.casefold() in BINARY_SUFFIXES
            or name in {item.casefold() for item in SENSITIVE_FILENAMES}
            or (name.startswith(".env.") and name != ".env.example")
            or path.suffix.casefold() in SENSITIVE_SUFFIXES
            or name.endswith((".sqlite", ".sqlite3", ".db", ".log")))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def inspect_repository(path: Path, max_files: int = 5000) -> RepositoryInfo:
    root = path.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository does not exist: {root}")
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        dirs[:] = sorted(d for d in dirs if not is_excluded(current_path / d, root))
        for name in sorted(names):
            candidate = current_path / name
            if not is_excluded(candidate, root):
                files.append(candidate.relative_to(root))
                if len(files) >= max_files:
                    break
        if len(files) >= max_files:
            break
    is_git = (root / ".git").exists()
    if not is_git:
        return RepositoryInfo(root, False, tuple(files), limitations=("not a Git repository",))
    head_result = _git(root, "rev-parse", "HEAD")
    branch_result = _git(root, "branch", "--show-current")
    origin_result = _git(root, "remote", "get-url", "origin")
    status_result = _git(root, "status", "--porcelain=v1")
    limitations = []
    if head_result.returncode: limitations.append("repository has no base commit")
    if origin_result.returncode: limitations.append("repository has no origin")
    return RepositoryInfo(root, True, tuple(files), head_result.stdout.strip() or None,
                          origin_result.stdout.strip() or None, branch_result.stdout.strip() or None,
                          not bool(status_result.stdout.strip()) if status_result.returncode == 0 else None,
                          tuple(limitations))


def collect_context(path: Path, max_files: int = 30, max_chars: int = 80_000,
                    references: tuple[str, ...] = ()) -> str:
    info = inspect_repository(path)
    refs = {Path(item).as_posix().casefold() for item in references}
    preferred = [p for p in info.files if p.as_posix().casefold() in refs]
    preferred += [p for p in info.files if p not in preferred and (p.name in {"AGENTS.md", "README.md"} or p.parts[:1] in {("docs",), (".ai-team",)})]
    source = [p for p in info.files if p not in preferred]
    chunks: list[str] = []
    used = 0
    for relative in preferred + source:
        if len(chunks) >= max_files:
            break
        target = info.path / relative
        try:
            if target.stat().st_size > min(max_chars, 100_000):
                continue
            content = target.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        block = f"\n--- FILE: {relative.as_posix()} ---\n{content}"
        remaining = max_chars - used
        if remaining <= 0:
            break
        chunks.append(block[:remaining])
        used += min(len(block), remaining)
    return "".join(chunks)


_PATHSPECS = [".", ":(exclude)**/.env", ":(exclude)**/.env.*", ":(exclude)**/*.key",
              ":(exclude)**/*.pem", ":(exclude)**/*.p12", ":(exclude)**/*.pfx",
              ":(exclude)**/credentials.json", ":(exclude)**/secrets.json",
              ":(exclude)**/omniroute-data/**", ":(exclude)**/.ai-team/logs/**"]


def change_scope(path: Path, max_chars: int = 100_000) -> ChangeScope:
    root = path.resolve()
    if not (root / ".git").exists():
        return ChangeScope("", "", ())
    staged = _git(root, "diff", "--cached", "--", *_PATHSPECS).stdout[-max_chars:]
    unstaged = _git(root, "diff", "--", *_PATHSPECS).stdout[-max_chars:]
    raw = _git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    untracked = tuple(Path(item) for item in raw.split("\0") if item and not is_excluded(root / item, root))
    return ChangeScope(staged, unstaged, untracked)


def git_diff(path: Path) -> str:
    scope = change_scope(path)
    pieces = []
    if scope.staged: pieces.append("STAGED:\n" + scope.staged)
    if scope.unstaged: pieces.append("UNSTAGED:\n" + scope.unstaged)
    if scope.untracked: pieces.append("UNTRACKED:\n" + "\n".join(p.as_posix() for p in scope.untracked))
    return "\n\n".join(pieces) or ("No Git change scope." if (path / ".git").exists() else "Repository is not initialized with Git.")


def detect_project_facts(root: Path) -> dict[str, object]:
    files = set(inspect_repository(root).files)
    languages: list[str] = []
    frameworks: list[str] = []
    commands: dict[str, list[str]] = {"build": [], "test": [], "lint": []}
    suffixes = {p.suffix.casefold() for p in files}
    if ".py" in suffixes:
        languages.append("Python")
        if Path("pyproject.toml") in files: commands["test"].append("python -m pytest")
    if ".js" in suffixes or ".ts" in suffixes: languages.append("JavaScript/TypeScript")
    if Path("package.json") in files:
        commands["build"].append("npm run build (candidate; verify script)")
        commands["test"].append("npm test (candidate; verify script)")
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8", errors="replace").lower()
        for name in ("django", "fastapi", "flask", "langgraph"):
            if name in text: frameworks.append(name)
        if "ruff" in text: commands["lint"].append("ruff check .")
    security_areas = [p.as_posix() for p in files if any(word in p.as_posix().casefold() for word in ("auth", "security", "api", "secret", "payment", "upload"))][:50]
    return {"languages": languages or ["UNKNOWN"], "frameworks": frameworks or ["UNKNOWN"], "commands": commands, "security_areas": security_areas}
