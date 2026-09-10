# Project Onboarding

Run `python -m ai_team init "C:\path\to\project"`. The command inspects the target and creates only missing files in the documentation contract. Review `.ai-team/TEAM_BRIEF.md`, replace unknowns with the product objective where appropriate, and record repository-specific commands and constraints in `AGENTS.md`.

Then run:

```powershell
python -m ai_team run "C:\path\to\project" --objective "A concrete, testable business or product objective"
```

Use `status` to inspect progress or `resume` after interruption. A human remains responsible for business acceptance and any optional deploy, merge, or push.

For chat-based operation, open the exact target folder as the VS Code workspace and use Continue Agent mode with `OmniRoute AI Team Auto`. The global configuration starts the framework MCP server in the open workspace; `ai_team_workspace` confirms the binding before work begins. The team can then search and read safe workspace files, check GitHub connectivity, and run allowlisted local build/test tools without project-local Continue configuration or manual Python commands.

## Giving the team durable context

Use `.ai-team/PROJECT_CONTEXT.md` for stable facts that are not obvious from source code, such as the canonical entry point, deployment boundaries, business terminology, or a required test command. In chat, say “remember that …” and the agent will use `ai_team_remember`. Notes are timestamped and included in later runs. Do not place credentials or secrets there.

Keep these sources distinct:

- `AGENTS.md`: repository rules, constraints, and verified commands.
- `.ai-team/PROJECT_CONTEXT.md`: user-confirmed durable facts.
- source and documentation: current implementation evidence.
- the current objective: task-specific intent and acceptance outcome.

Before claiming a file is absent, the team must use objective-aware repository search. Context collection includes a safe file inventory and ranks filenames and file contents against the current objective, avoiding the previous alphabetical first-files limitation.

If `ai_team_workspace` reports `configured_umbrella`, the open folder is a project container rather than the source checkout. Follow its `next_action` and `AGENTS.md`: validate `.ai-workspace.json`, prepare the isolated task worktree, and open that returned worktree in VS Code. `.ai-worktrees`, temporary folders, dependencies, and caches are excluded from ambient search.
