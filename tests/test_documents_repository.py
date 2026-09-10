from pathlib import Path

import pytest

from ai_team.documents import DOCS, bootstrap_project
from ai_team.repository import (
    collect_context,
    find_repository_matches,
    inspect_repository,
    read_project_context,
    read_repository_file,
    remember_project_context,
)


def test_document_bootstrap_is_non_destructive(tmp_path: Path):
    (tmp_path / "README.md").write_text("existing", encoding="utf-8")
    created = bootstrap_project(tmp_path)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "existing"
    assert (tmp_path / "AGENTS.md").exists()
    assert all((tmp_path / "docs" / name).exists() for name in DOCS)
    assert (tmp_path / ".ai-team" / "test-results").is_dir()
    assert created


def test_repository_excludes_generated_and_binary_content(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "index.js").write_text(
        "ignored", encoding="utf-8"
    )
    (tmp_path / ".ai-worktrees" / "old-task").mkdir(parents=True)
    (tmp_path / ".ai-worktrees" / "old-task" / "app.py").write_text(
        "ignored", encoding="utf-8"
    )
    (tmp_path / "tmp" / "pytest-stale").mkdir(parents=True)
    (tmp_path / "tmp" / "pytest-stale" / "result.txt").write_text(
        "ignored", encoding="utf-8"
    )
    (tmp_path / "image.png").write_bytes(b"png")
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=", encoding="utf-8")
    files = inspect_repository(tmp_path).files
    assert Path("src/app.py") in files
    assert not any("node_modules" in path.parts for path in files)
    assert not any(".ai-worktrees" in path.parts for path in files)
    assert not any("tmp" in path.parts for path in files)
    assert Path("image.png") not in files
    assert Path(".env") not in files
    assert Path(".env.example") in files


def test_context_prioritizes_objective_and_includes_safe_inventory(tmp_path: Path):
    for index in range(40):
        (tmp_path / f"file-{index:02}.txt").write_text("ordinary", encoding="utf-8")
    target = tmp_path / "src" / "important_service.py"
    target.parent.mkdir()
    target.write_text("def rare_symbol_name():\n    return 42\n", encoding="utf-8")

    context = collect_context(tmp_path, max_files=2, query="find rare_symbol_name")

    assert "SAFE REPOSITORY FILE INVENTORY" in context
    assert "src/important_service.py" in context
    assert "def rare_symbol_name" in context


def test_find_and_read_safe_workspace_files(tmp_path: Path):
    target = tmp_path / "src" / "feature.py"
    target.parent.mkdir()
    target.write_text("FEATURE_FLAG = 'durable-context'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=private", encoding="utf-8")

    matches = find_repository_matches(tmp_path, "durable-context")

    assert matches[0]["path"] == "src/feature.py"
    assert "FEATURE_FLAG" in read_repository_file(tmp_path, "src/feature.py")
    with pytest.raises(ValueError, match="secret files"):
        read_repository_file(tmp_path, ".env")
    with pytest.raises(ValueError, match="inside the active workspace"):
        read_repository_file(tmp_path, "../outside.txt")


def test_project_context_is_durable_and_rejects_secrets(tmp_path: Path):
    remember_project_context(tmp_path, "The canonical entry point is src/main.py.")

    assert "canonical entry point" in read_project_context(tmp_path)
    with pytest.raises(ValueError, match="Do not store"):
        remember_project_context(tmp_path, "api_key=do-not-save-this")
