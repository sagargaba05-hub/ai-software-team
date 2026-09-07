# Project Onboarding

Run `python -m ai_team init "C:\path\to\project"`. The command inspects the target and creates only missing files in the documentation contract. Review `.ai-team/TEAM_BRIEF.md`, replace unknowns with the product objective where appropriate, and record repository-specific commands and constraints in `AGENTS.md`.

Then run:

```powershell
python -m ai_team run "C:\path\to\project" --objective "A concrete, testable business or product objective"
```

Use `status` to inspect progress or `resume` after interruption. A human remains responsible for business acceptance and any optional deploy, merge, or push.

For chat-based operation, configure Continue with the framework's `ai_team.mcp_server`, open any target repository, and use Agent mode. Global Continue rules can call `ai_team_status` for progress questions and `ai_team_run` for a concrete build or fix request without requiring project-local configuration or manual Python commands.
