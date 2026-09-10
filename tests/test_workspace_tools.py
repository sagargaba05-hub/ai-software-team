from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_team.workspace_tools import _github_repository_name, run_local_program


def test_github_repository_name_supports_https_and_ssh():
    assert (
        _github_repository_name("https://github.com/example/project.git")
        == "example/project"
    )
    assert (
        _github_repository_name("git@github.com:example/project.git")
        == "example/project"
    )
    assert _github_repository_name("https://example.com/example/project.git") is None


def test_local_execution_requires_explicit_global_enablement(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("AI_TEAM_LOCAL_EXECUTION_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        run_local_program(tmp_path, "python", ["--version"])


def test_local_execution_runs_allowlisted_program_without_shell(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("AI_TEAM_LOCAL_EXECUTION_ENABLED", "true")
    script = tmp_path / "check.py"
    script.write_text("print('workspace-execution-ok')\n", encoding="utf-8")

    result = run_local_program(tmp_path, "python", ["check.py"])

    assert result["exit_code"] == 0
    assert result["output"] == "workspace-execution-ok"


def test_local_execution_blocks_inline_code_mutating_git_and_escape(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("AI_TEAM_LOCAL_EXECUTION_ENABLED", "true")
    with pytest.raises(ValueError, match="Inline code"):
        run_local_program(tmp_path, "python", ["-c", "print('unsafe')"])
    with pytest.raises(ValueError, match="not read-only"):
        run_local_program(tmp_path, "git", ["push"])
    with pytest.raises(ValueError, match="inside the active workspace"):
        run_local_program(tmp_path, "python", ["--version"], "..")
    with pytest.raises(ValueError, match="cannot escape"):
        run_local_program(tmp_path, "python", [str(tmp_path.parent / "outside.py")])
    with pytest.raises(ValueError, match="limited"):
        run_local_program(tmp_path, "python", ["-m", "pip", "install", "package"])
    with pytest.raises(ValueError, match="limited"):
        run_local_program(tmp_path, "npm", ["install"])


def test_local_execution_allows_read_only_git(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_TEAM_LOCAL_EXECUTION_ENABLED", "true")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)

    result = run_local_program(tmp_path, "git", ["status", "--short"])

    assert result["exit_code"] == 0
