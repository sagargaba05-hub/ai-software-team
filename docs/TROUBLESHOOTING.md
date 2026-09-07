# Troubleshooting

## PowerShell blocks npm shims

Use the `.cmd` shim (`codex.cmd`, `omniroute.cmd`, `npm.cmd`) or call the executable by absolute path. A restrictive execution policy may block `.ps1` shims even when the tool is correctly installed.

## Python launcher says no Python is installed

Use the working `python.exe` command directly. The Windows `py.exe` launcher can be stale even when Python itself is installed.

## OmniRoute is unavailable

Run `omniroute health`, then use `.\scripts\start-omniroute.ps1`. The framework launcher uses its own Git-ignored data directory and a five-minute execution deadline for large local models. If the machine's older default instance reports an encrypted database without `STORAGE_ENCRYPTION_KEY`, restore the original key; do not delete or replace that database unless its data is intentionally discarded.

The launcher explicitly binds the server to `127.0.0.1`. Verify that address, not only the port, with `Get-NetTCPConnection -LocalPort 20128 -State Listen`.

## Continue cannot see the AI-team tools

Run **Developer: Reload Window** in VS Code after changing `C:\Users\sagar\.continue\config.yaml`. In Continue, select `OmniRoute Qwen Coder`, switch to Agent mode, and confirm that the `AI Software Team` MCP server and its four `ai_team_*` tools are enabled. Check that OmniRoute is listening on `127.0.0.1:20128` and run `python -m ai_team doctor` from the framework virtual environment.

Do not select the older `localhost:8080` model when the intended path is OmniRoute. Direct Ollama entries on port `11434` bypass OmniRoute and the framework's routing layer.

## Model returned an empty diff fence

Current versions treat an empty or non-patch `diff` fence as no change. A malformed patch containing real unified-diff headers still fails validation. Use a concrete implementation objective for `run`; use `status` for progress questions.

## A required Ollama model is missing

Run `ollama pull qwen3-coder:30b` or `ollama pull gpt-oss:20b`, then rerun `python -m ai_team doctor`.

## Resume a stopped run

Run `python -m ai_team status <repo>` first, then `python -m ai_team resume <repo>`. State is stored at `<repo>\.ai-team\state.sqlite3`.

## Codex authentication fails doctor

The framework prefers the authenticated Codex binary bundled with the OpenAI VS Code extension on Windows, then falls back to standalone CLI installations. Set `CODEX_BINARY` to choose a specific executable. If none is authenticated, run `codex login` interactively. Local workers and offline dry runs remain available; set `CODEX_ENABLED=false` only when the lack of escalation is intentional.
