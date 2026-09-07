import subprocess

import pytest

from ai_team.repository import change_scope, collect_context, inspect_repository
from ai_team.state_store import StateError, StateStore


def test_state_lease_rejects_conflicting_active_run(tmp_path):
    store = StateStore(tmp_path)
    store.save({"schema_version": 2, "run_id": "one", "status": "RUNNING"})
    store.acquire("one")
    with pytest.raises(StateError, match="Another active run"):
        store.acquire("two")


def test_state_read_is_read_only_when_missing(tmp_path):
    assert StateStore.read(tmp_path) is None
    assert not (tmp_path / ".ai-team").exists()


def test_unknown_state_schema_fails_closed(tmp_path):
    store = StateStore(tmp_path)
    with pytest.raises(StateError, match="Unsupported"):
        store.save({"schema_version": 999, "run_id": "x", "status": "RUNNING"})


def test_nested_case_insensitive_exclusions_and_context_bounds(tmp_path):
    (tmp_path / "Src").mkdir(); (tmp_path / "Src/app.py").write_text("x" * 100, encoding="utf-8")
    (tmp_path / "Nested/NoDe_MoDuLeS/p").mkdir(parents=True)
    (tmp_path / "Nested/NoDe_MoDuLeS/p/a.js").write_text("secret", encoding="utf-8")
    (tmp_path / "Nested/.ENV.Production").write_text("TOKEN=x", encoding="utf-8")
    info = inspect_repository(tmp_path)
    assert info.files == (type(info.files[0])("Src/app.py"),)
    assert len(collect_context(tmp_path, max_files=1, max_chars=50)) <= 50


def test_change_scope_includes_staged_unstaged_and_untracked(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "a.txt"], check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    (tmp_path / "b.txt").write_text("new", encoding="utf-8")
    scope = change_scope(tmp_path)
    assert "a.txt" in scope.staged and "a.txt" in scope.unstaged
    assert type(scope.untracked[0])("b.txt") in scope.untracked
