# System Architecture

## Components

- `cli.py` exposes doctor, init, run, status, resume, and dry-run commands.
- `supervisor.py` owns the LangGraph workflow and its QA/review retry edges.
- `skills.py` loads the nine user-level `SKILL.md` files and validates front matter.
- `documents.py` bootstraps project documentation without overwriting existing facts.
- `repository.py` inspects repositories, filters generated/vendor content, and collects Git diffs.
- `models.py` sends role prompts to an OpenAI-compatible OmniRoute endpoint.
- `executor.py` builds bounded role context and records stage artifacts.
- `state_store.py` persists resumable state in project-local SQLite.
- `doctor.py` checks the required local toolchain and connectivity.
- `mcp_server.py` exposes doctor, status, run, and resume as local stdio MCP tools for IDE clients such as Continue.

## IDE entry point

Continue sends chat and Agent-mode model requests to OmniRoute's OpenAI-compatible endpoint. Its local MCP host launches the framework with the repository virtual environment and communicates over stdio. The bridge is globally available and accepts any existing project directory supplied explicitly by the IDE agent. It uses fixed subprocess argument arrays rather than a shell, rejects missing directories and empty or oversized objectives, captures child output, and never places protocol logging on stdout.

OmniRoute provides model transport and provider/model selection. The LangGraph supervisor—not OmniRoute—owns role sequencing, persisted state, retries, escalation, and release gates.

## State flow

`START -> inspect -> bootstrap -> brief -> product -> architect -> work orders -> developer -> refactor -> QA`

QA failure returns to Developer until the configured retry limit. QA success advances to Review. Review failure routes to Architect when the finding identifies an architecture issue; otherwise it routes to Developer. Every review rework passes QA again. Only QA PASS, Review PASS, and completed Documentation can unlock Release PASS.

The framework exchanges repository artifacts and a bounded set of relevant files. It excludes dependency, generated, cache, VCS, and binary content.

## Safety

The framework does not push, merge, deploy, delete databases, or approve destructive migrations. Codex escalation is separately bounded and disabled when `CODEX_ENABLED=false`.
