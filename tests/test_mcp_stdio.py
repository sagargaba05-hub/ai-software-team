from __future__ import annotations

import asyncio

from ai_team import mcp_server


def test_mcp_server_lists_tools_and_returns_status(tmp_path):
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "ai_team_doctor",
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
