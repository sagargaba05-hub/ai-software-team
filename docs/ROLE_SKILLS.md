# Role Skills

The authoritative role definitions live under `C:\Users\sagar\.agents\skills\ai-team-*\SKILL.md`. `ai_team.skills.SkillLoader` reads YAML front matter plus the complete Markdown body for each stage.

Repository-local `AGENTS.md` and project documentation supplement those global rules with project facts and constraints. They do not replace the global role boundary unless an explicit repository override is recorded.

Validate the global skills with the Codex skill validator or `python -m ai_team doctor`.

