from pathlib import Path

import pytest

from ai_team import mcp_server


def test_repository_uses_any_existing_directory(tmp_path):
    assert mcp_server._repository(str(tmp_path)) == tmp_path.resolve()


def test_repository_dot_uses_server_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert mcp_server._repository(".") == tmp_path.resolve()


def test_repository_rejects_other_relative_directory():
    with pytest.raises(ValueError, match="other relative paths"):
        mcp_server._repository("another-project")


def test_repository_rejects_missing_directory(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        mcp_server._repository(str(tmp_path / "missing"))


def test_execute_uses_argument_list_without_shell(monkeypatch, tmp_path):
    captured = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)
    result = mcp_server._execute("run", Path(tmp_path), "Make a focused change")
    assert result == "ok"
    assert captured["command"][-2:] == ["--objective", "Make a focused change"]
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["stdin"] is mcp_server.subprocess.DEVNULL
    assert "shell" not in captured["kwargs"]
