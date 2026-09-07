# Reusable AI Software Team

A reusable, project-independent software-delivery framework. A LangGraph supervisor routes work through Product, Architecture, Development, Refactor, QA, Review, Documentation, and Release stages. Local model selection is hidden behind OmniRoute, while Codex is reserved for bounded escalation.

The nine user-level skills under `C:\Users\sagar\.agents\skills` are the single source of truth for role behavior. The framework reads those files at runtime; it does not duplicate role prompts.

## Setup (Windows PowerShell)

```powershell
cd "C:\Users\sagar\Desktop\AI tools\ai-software-team"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m ai_team doctor
```

Keep real secrets only in `.env`, which is ignored by Git. Start the isolated, large-model-safe OmniRoute instance before a live run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-omniroute.ps1
```

The launcher uses `omniroute-data` inside this repository and a five-minute local execution deadline. That data directory is Git-ignored and does not replace the machine's pre-existing OmniRoute database.

## Commands

```powershell
.\.venv\Scripts\python.exe -m ai_team init "C:\path\to\project"
.\.venv\Scripts\python.exe -m ai_team run "C:\path\to\project" --objective "Deliver the requested product outcome."
.\.venv\Scripts\python.exe -m ai_team status "C:\path\to\project"
.\.venv\Scripts\python.exe -m ai_team resume "C:\path\to\project"
```

`init` creates missing documentation and `.ai-team` artifacts without changing production code. `run` persists state in `.ai-team/state.sqlite3`. It never pushes, merges, deploys, or performs destructive migrations.

For an offline control-flow check:

```powershell
.\.venv\Scripts\python.exe -m ai_team dry-run .\sample-project
```

## Continue chat integration

Continue can use OmniRoute as an OpenAI-compatible chat and Agent-mode model. The user-level Continue config at `C:\Users\sagar\.continue\config.yaml` points `OmniRoute Qwen Coder` to `http://127.0.0.1:20128/v1` and starts `python -m ai_team.mcp_server` over stdio.

The MCP server exposes four tools:

- `ai_team_doctor`
- `ai_team_status`
- `ai_team_run`
- `ai_team_resume`

Open any target repository in VS Code, reload the window after configuration changes, select `OmniRoute Qwen Coder`, and use Continue's Agent mode. Global Continue rules tell the agent when to use each team tool. The MCP tools require the agent to supply the current repository path explicitly, preventing an omitted path from silently targeting a different project. No project-local Continue configuration is required. OmniRoute must be running before model conversations or live team runs.

## Operating model

```text
Product owner -> Continue/Codex/MCP entry point -> LangGraph supervisor -> specialist roles
              -> OmniRoute -> Ollama/free providers -> Git/tests/docs
              -> gated release report
```

See `docs/` for architecture, onboarding, routing, role skills, and troubleshooting.
