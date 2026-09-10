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

Continue can use OmniRoute as an OpenAI-compatible chat and Agent-mode model. The user-level Continue config at `C:\Users\sagar\.continue\config.yaml` points the single `OmniRoute AI Team Auto` model to `http://127.0.0.1:20128/v1` and starts `python -m ai_team.mcp_server` over stdio. Continue uses complete responses for this model and OmniRoute strips provider reasoning metadata before it reaches the chat.

The MCP server exposes workspace-aware tools for:

- exact workspace identity and AI-team health;
- repository search, safe file reading, and durable project context;
- read-only GitHub connection status;
- checked-in local Python/Node files, pytest, npm test/run scripts, and read-only Git commands; and
- initializing, starting, resuming, inspecting, and demonstrating an AI-team run.

Open any target repository as the VS Code workspace, reload the window after configuration changes, select `OmniRoute AI Team Auto`, and use Continue's Agent mode. The global MCP process is launched with that workspace as its working directory, so `repository="."` resolves to the open folder. The agent verifies this with `ai_team_workspace` before project work and searches the safe repository inventory before declaring a file missing. No project-local Continue configuration is required. OmniRoute must be running before model conversations or live team runs.

Local execution is intentionally bounded: commands are passed directly to an allowlist without a shell; inline code, path escape, generated/dependency directories, and mutating Git commands are rejected. GitHub authentication can be inspected, but commits, pushes, merges, deployment, destructive operations, and arbitrary shell access remain human-authorized actions.

## Operating model

```text
Product owner -> Continue/Codex/MCP entry point -> LangGraph supervisor -> specialist roles
              -> OmniRoute -> Ollama/free providers -> Git/tests/docs
              -> gated release report
```

See `docs/` for architecture, onboarding, routing, role skills, and troubleshooting.
