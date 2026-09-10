from __future__ import annotations

import json
from pathlib import Path

from .repository import detect_project_facts

DOCS = [
    "PRODUCT.md",
    "REQUIREMENTS.md",
    "ARCHITECTURE.md",
    "DECISIONS.md",
    "TASKS.md",
    "TEST_PLAN.md",
    "SECURITY.md",
    "RUNBOOK.md",
    "CHANGELOG.md",
]


def _write_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def bootstrap_project(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    created: list[Path] = []
    candidates = {
        root
        / "README.md": "# Project\n\nProject facts are not yet documented. Update from repository evidence.\n",
        root
        / "AGENTS.md": "# Repository Instructions\n\n## Constraints\n\n- Preserve existing product behavior unless requirements explicitly change it.\n- Do not read or edit generated, vendor, dependency, cache, or secret files.\n- Record repository-specific build and test commands here once verified.\n- Global AI-team role behavior is supplemented by this file; explicit repository constraints take precedence.\n",
    }
    for name in DOCS:
        title = name.removesuffix(".md").replace("_", " ").title()
        candidates[root / "docs" / name] = (
            f"# {title}\n\nStatus: Unknown - resolve from repository evidence before release.\n"
        )
    candidates[root / ".ai-team" / "TEAM_BRIEF.md"] = (
        "# Team Brief\n\n## Objective\n\nUnknown - set with `ai_team run --objective`.\n\n## Constraints\n\nResolve from AGENTS.md and repository evidence.\n"
    )
    candidates[root / ".ai-team" / "PROJECT_CONTEXT.md"] = (
        "# Project Context\n\n"
        "Durable facts explicitly provided by the user. Do not infer secrets.\n"
    )
    candidates[root / ".ai-team" / "RELEASE_REPORT.md"] = (
        "# Release Report\n\nStatus: NOT_RUN\n"
    )
    for target, content in candidates.items():
        if _write_missing(target, content):
            created.append(target)
    for folder in [
        "work-orders",
        "test-results",
        "reviews",
        "security",
        "escalations",
        "logs",
        "demo",
    ]:
        directory = root / ".ai-team" / folder
        directory.mkdir(parents=True, exist_ok=True)
        keep = directory / ".gitkeep"
        if _write_missing(keep, ""):
            created.append(keep)
    state_json = root / ".ai-team" / "state.json"
    if _write_missing(
        state_json,
        json.dumps({"status": "INITIALIZED", "stage": "bootstrap"}, indent=2) + "\n",
    ):
        created.append(state_json)
    onboarding = root / ".ai-team" / "onboarding.json"
    if _write_missing(
        onboarding, json.dumps(detect_project_facts(root), indent=2) + "\n"
    ):
        created.append(onboarding)
    return created
