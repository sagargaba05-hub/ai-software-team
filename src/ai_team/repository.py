from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .constants import (
    BINARY_SUFFIXES,
    EXCLUDED_DIRS,
    SENSITIVE_FILENAMES,
    SENSITIVE_SUFFIXES,
)


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


PROJECT_CONTEXT = Path(".ai-team") / "PROJECT_CONTEXT.md"
_QUERY_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@/\\-]*")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "current",
    "do",
    "file",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "project",
    "repository",
    "that",
    "the",
    "this",
    "to",
    "with",
}
_SENSITIVE_NOTE = re.compile(
    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|secret|private[_ -]?key)\b\s*[:=]\s*\S+"
)


def is_excluded(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    parts = tuple(part.casefold() for part in relative.parts)
    excluded = {item.casefold() for item in EXCLUDED_DIRS}
    if any(part in excluded for part in parts):
        return True
    if len(parts) >= 2 and parts[0] == ".ai-team" and parts[1] in {"runtime", "logs"}:
        return True
    name = path.name.casefold()
    return (
        path.suffix.casefold() in BINARY_SUFFIXES
        or name in {item.casefold() for item in SENSITIVE_FILENAMES}
        or (name.startswith(".env.") and name != ".env.example")
        or path.suffix.casefold() in SENSITIVE_SUFFIXES
        or name.endswith((".sqlite", ".sqlite3", ".db", ".log"))
    )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


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
        return RepositoryInfo(
            root, False, tuple(files), limitations=("not a Git repository",)
        )
    head_result = _git(root, "rev-parse", "HEAD")
    branch_result = _git(root, "branch", "--show-current")
    origin_result = _git(root, "remote", "get-url", "origin")
    status_result = _git(root, "status", "--porcelain=v1")
    limitations = []
    if head_result.returncode:
        limitations.append("repository has no base commit")
    if origin_result.returncode:
        limitations.append("repository has no origin")
    return RepositoryInfo(
        root,
        True,
        tuple(files),
        head_result.stdout.strip() or None,
        origin_result.stdout.strip() or None,
        branch_result.stdout.strip() or None,
        not bool(status_result.stdout.strip())
        if status_result.returncode == 0
        else None,
        tuple(limitations),
    )


def _query_terms(query: str) -> tuple[str, ...]:
    terms: list[str] = []
    for raw in _QUERY_TOKEN.findall(query):
        normalized = raw.replace("\\", "/").strip("./").casefold()
        for candidate in (normalized, Path(normalized).name):
            if len(candidate) < 2 or candidate in _STOP_WORDS or candidate in terms:
                continue
            terms.append(candidate)
    return tuple(terms[:40])


def _read_safe_text(root: Path, relative: Path, max_chars: int = 100_000) -> str | None:
    target = root / relative
    try:
        if target.stat().st_size > max_chars:
            return None
        return target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _rank_files(
    info: RepositoryInfo, query: str = "", references: tuple[str, ...] = ()
) -> list[Path]:
    reference_set = {Path(item).as_posix().casefold() for item in references}
    terms = _query_terms(query)
    scored: list[tuple[int, str, Path]] = []
    for relative in info.files:
        path_text = relative.as_posix().casefold()
        name = relative.name.casefold()
        score = 0
        if path_text in reference_set:
            score += 10_000
        if relative == PROJECT_CONTEXT:
            score += 9_000
        if relative.name in {"AGENTS.md", "README.md"}:
            score += 2_000
        if relative.parts[:1] in {("docs",), (".ai-team",)}:
            score += 500
        for term in terms:
            if term == path_text or term == name:
                score += 4_000
            elif term in path_text:
                score += 800
        if terms and score < 4_000:
            content = _read_safe_text(info.path, relative, 100_000)
            if content:
                folded = content.casefold()
                score += min(1_200, sum(120 for term in terms if term in folded))
        scored.append((score, path_text, relative))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


def find_repository_matches(
    path: Path, query: str, max_results: int = 50
) -> list[dict[str, object]]:
    query = query.strip()
    if not query:
        raise ValueError("Search query must not be empty.")
    if not 1 <= max_results <= 200:
        raise ValueError("max_results must be between 1 and 200.")
    info = inspect_repository(path)
    terms = _query_terms(query)
    phrase = query.replace("\\", "/").casefold()
    matches: list[dict[str, object]] = []
    for relative in _rank_files(info, query):
        path_text = relative.as_posix()
        path_folded = path_text.casefold()
        snippets: list[dict[str, object]] = []
        content = _read_safe_text(info.path, relative, 100_000)
        if content:
            for number, line in enumerate(content.splitlines(), 1):
                folded = line.casefold()
                if phrase in folded or any(term in folded for term in terms):
                    snippets.append({"line": number, "text": line.strip()[:300]})
                    if len(snippets) == 3:
                        break
        path_hit = phrase in path_folded or any(term in path_folded for term in terms)
        if path_hit or snippets:
            matches.append(
                {"path": path_text, "path_match": path_hit, "snippets": snippets}
            )
            if len(matches) == max_results:
                break
    return matches


def resolve_repository_file(path: Path, value: str) -> Path:
    root = path.resolve()
    candidate = Path(value).expanduser()
    candidate = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("File must stay inside the active workspace.")
    if not candidate.is_file():
        raise FileNotFoundError(f"Workspace file does not exist: {value}")
    if is_excluded(candidate, root):
        raise ValueError(
            "Generated, dependency, binary, cache, and secret files are not readable."
        )
    return candidate


def read_repository_file(path: Path, value: str, max_chars: int = 80_000) -> str:
    if not 1_000 <= max_chars <= 500_000:
        raise ValueError("max_chars must be between 1000 and 500000.")
    target = resolve_repository_file(path, value)
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Workspace file is not UTF-8 text.") from exc
    relative = target.relative_to(path.resolve()).as_posix()
    suffix = "\n[TRUNCATED]" if len(content) > max_chars else ""
    return f"FILE: {relative}\n{content[:max_chars]}{suffix}"


def read_project_context(path: Path) -> str:
    target = path.resolve() / PROJECT_CONTEXT
    if not target.is_file():
        return "# Project Context\n\nNo durable project context has been recorded.\n"
    return target.read_text(encoding="utf-8", errors="replace")


def remember_project_context(path: Path, note: str) -> Path:
    root = path.resolve()
    note = " ".join(note.strip().split())
    if not note:
        raise ValueError("Context note must not be empty.")
    if len(note) > 4_000:
        raise ValueError("Context note exceeds 4000 characters.")
    if _SENSITIVE_NOTE.search(note):
        raise ValueError(
            "Do not store passwords, tokens, API keys, or private keys in project context."
        )
    target = root / PROJECT_CONTEXT
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(
            "# Project Context\n\nDurable facts explicitly provided by the user. Do not infer secrets.\n",
            encoding="utf-8",
        )
    timestamp = datetime.now(UTC).isoformat()
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n- [{timestamp}] {note}\n")
    return target


def collect_context(
    path: Path,
    max_files: int = 30,
    max_chars: int = 80_000,
    references: tuple[str, ...] = (),
    query: str = "",
) -> str:
    info = inspect_repository(path)
    inventory_budget = min(max_chars, 20_000, max(1_000, max_chars // 5))
    inventory_text = "\n".join(relative.as_posix() for relative in info.files)
    inventory = f"--- SAFE REPOSITORY FILE INVENTORY ({len(info.files)} files) ---\n{inventory_text}"
    if len(inventory) > inventory_budget:
        inventory = inventory[:inventory_budget] + "\n[INVENTORY TRUNCATED]"
    chunks: list[str] = [inventory]
    used = len(inventory)
    included = 0
    for relative in _rank_files(info, query, references):
        if included >= max_files:
            break
        content = _read_safe_text(info.path, relative, min(max_chars, 100_000))
        if content is None:
            continue
        block = f"\n--- FILE: {relative.as_posix()} ---\n{content}"
        remaining = max_chars - used
        if remaining <= 0:
            break
        chunks.append(block[:remaining])
        used += min(len(block), remaining)
        included += 1
    return "".join(chunks)[:max_chars]


_PATHSPECS = [
    ".",
    ":(exclude)**/.env",
    ":(exclude)**/.env.*",
    ":(exclude)**/*.key",
    ":(exclude)**/*.pem",
    ":(exclude)**/*.p12",
    ":(exclude)**/*.pfx",
    ":(exclude)**/credentials.json",
    ":(exclude)**/secrets.json",
    ":(exclude)**/omniroute-data/**",
    ":(exclude)**/.ai-team/logs/**",
]


def change_scope(path: Path, max_chars: int = 100_000) -> ChangeScope:
    root = path.resolve()
    if not (root / ".git").exists():
        return ChangeScope("", "", ())
    staged = _git(root, "diff", "--cached", "--", *_PATHSPECS).stdout[-max_chars:]
    unstaged = _git(root, "diff", "--", *_PATHSPECS).stdout[-max_chars:]
    raw = _git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    untracked = tuple(
        Path(item)
        for item in raw.split("\0")
        if item and not is_excluded(root / item, root)
    )
    return ChangeScope(staged, unstaged, untracked)


def changed_paths(path: Path) -> tuple[str, ...]:
    root = path.resolve()
    if not (root / ".git").exists():
        return ()
    result = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if result.returncode != 0:
        return ()
    entries = result.stdout.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        if not entry:
            index += 1
            continue
        status = entry[:2]
        value = entry[3:] if len(entry) > 3 else ""
        if value and value not in paths:
            paths.append(value)
        if "R" in status or "C" in status:
            index += 1
            if index < len(entries) and entries[index] and entries[index] not in paths:
                paths.append(entries[index])
        index += 1
    return tuple(paths)


def git_diff(path: Path) -> str:
    scope = change_scope(path)
    pieces = []
    if scope.staged:
        pieces.append("STAGED:\n" + scope.staged)
    if scope.unstaged:
        pieces.append("UNSTAGED:\n" + scope.unstaged)
    if scope.untracked:
        pieces.append("UNTRACKED:\n" + "\n".join(p.as_posix() for p in scope.untracked))
    return "\n\n".join(pieces) or (
        "No Git change scope."
        if (path / ".git").exists()
        else "Repository is not initialized with Git."
    )


def detect_project_facts(root: Path) -> dict[str, object]:
    files = set(inspect_repository(root).files)
    languages: list[str] = []
    frameworks: list[str] = []
    commands: dict[str, list[str]] = {"build": [], "test": [], "lint": []}
    suffixes = {p.suffix.casefold() for p in files}
    if ".py" in suffixes:
        languages.append("Python")
        if Path("pyproject.toml") in files:
            commands["test"].append("python -m pytest")
    if ".js" in suffixes or ".ts" in suffixes:
        languages.append("JavaScript/TypeScript")
    if Path("package.json") in files:
        commands["build"].append("npm run build (candidate; verify script)")
        commands["test"].append("npm test (candidate; verify script)")
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8", errors="replace").lower()
        for name in ("django", "fastapi", "flask", "langgraph"):
            if name in text:
                frameworks.append(name)
        if "ruff" in text:
            commands["lint"].append("ruff check .")
    security_areas = [
        p.as_posix()
        for p in files
        if any(
            word in p.as_posix().casefold()
            for word in ("auth", "security", "api", "secret", "payment", "upload")
        )
    ][:50]
    return {
        "languages": languages or ["UNKNOWN"],
        "frameworks": frameworks or ["UNKNOWN"],
        "commands": commands,
        "security_areas": security_areas,
    }
