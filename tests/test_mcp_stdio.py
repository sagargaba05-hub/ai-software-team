from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ai_team import mcp_server


def test_mcp_server_lists_tools_and_returns_status(tmp_path):
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "ai_team_doctor",
        "ai_team_workspace",
        "ai_team_find",
        "ai_team_read",
        "ai_team_context",
        "ai_team_remember",
        "ai_team_run_local",
        "ai_team_github_status",
        "ai_team_status",
        "ai_team_run",
        "ai_team_resume",
        "ai_team_init",
        "ai_team_demo",
    }

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "ai_team_status",
            {"repository": str(tmp_path)},
        )
    )
    assert "NOT_INITIALIZED" in result[0][0].text


def test_stdio_server_binds_dot_to_launch_workspace(tmp_path: Path):
    (tmp_path / "known-file.txt").write_text(
        "workspace-binding-proof\n", encoding="utf-8"
    )
    (tmp_path / "check.py").write_text("print('local-tool-proof')\n", encoding="utf-8")

    async def exercise_server():
        environment = dict(os.environ)
        environment["AI_TEAM_LOCAL_EXECUTION_ENABLED"] = "true"
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "ai_team.mcp_server"],
            cwd=tmp_path,
            env=environment,
        )
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            workspace = await session.call_tool("ai_team_workspace", {})
            found = await session.call_tool(
                "ai_team_find", {"query": "workspace-binding-proof"}
            )
            executed = await session.call_tool(
                "ai_team_run_local",
                {"program": "python", "arguments": ["check.py"]},
            )
            return workspace, found, executed

    workspace, found, executed = asyncio.run(exercise_server())

    workspace_data = json.loads(workspace.content[0].text)
    found_data = json.loads(found.content[0].text)
    executed_data = json.loads(executed.content[0].text)
    assert Path(workspace_data["workspace"]) == tmp_path.resolve()
    assert found_data["matches"][0]["path"] == "known-file.txt"
    assert executed_data["exit_code"] == 0
    assert executed_data["output"] == "local-tool-proof"


def test_workspace_reports_configured_umbrella(monkeypatch, tmp_path: Path):
    (tmp_path / ".ai-workspace.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "expected_remote": "https://github.com/example/project.git",
                "git_admin_path": "project",
                "base_branch": "main",
                "worktree_root": ".ai-worktrees",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = json.loads(mcp_server.ai_team_workspace())

    assert result["workspace_kind"] == "configured_umbrella"
    assert result["workspace_configuration"]["git_admin_path"] == "project"
    assert "isolated worktree" in result["next_action"]
