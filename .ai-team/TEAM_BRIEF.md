# Team Brief

## Objective

Complete and verify the reusable, local-first, multi-model AI software team in this repository. The system must accept a business/software requirement, select appropriate specialist roles, route routine work through local models, independently review significant implementation, invoke Codex only under explicit bounded escalation rules, keep documentation current, and enforce an evidence-based final quality gate.

## Approved model architecture

- Qwen3-Coder 30B is the primary local implementation model.
- GPT-OSS 20B is the independent local reviewer and reasoning model.
- Codex/GPT is a paid, bounded escalation route and must not be used for routine work.
- Optional cloud models may be used only when currently classified as local/free or an acceptable no-billing free tier; the core system must not depend on them.
- OmniRoute is the replaceable OpenAI-compatible routing abstraction, not the workflow authority.

## Required capabilities

- Separate role selection from model routing.
- Provide Team Lead, Architect, Developer, Debugger, Reviewer, Tester, Security, Documentation, and Final Quality Gate responsibilities with entry conditions, outputs, preferred/fallback model, escalation conditions, and completion criteria.
- Provide explicit normal and premium routing policies, three-cycle maximum local repair policy, usage/escalation logging, context minimisation, provider failure handling, credential protection, reusable project bootstrap, health checks, and feature/bugfix/refactor/review/security workflows.
- Reuse healthy installed tools and models; do not reinstall unnecessarily.
- Verify local models, OmniRoute routing, and an end-to-end controlled demonstration covering Qwen implementation routing, GPT-OSS review routing, simulated escalation, and non-use of Codex for routine work.

## Constraints

- Work directly in `C:\Users\sagar\Desktop\AI tools\ai-software-team`, as explicitly confirmed by the user.
- Preserve useful existing implementation and user changes.
- Do not add mandatory paid providers, unnecessary frameworks, containers, queues, databases, SaaS dependencies, or competing VS Code agent extensions.
- Do not expose credentials, push, merge, deploy, or perform destructive Git operations.
- Documentation is mandatory and must describe verified behavior only.
- "No bypasses" means no requirements or verification shortcuts; it does not require a remote repository or moving work out of the open folder.

## Repository note

The current folder is an uncommitted Git repository with no origin or base commit. The user explicitly requires in-place execution. Git-based comparisons must therefore include untracked files or use recorded task artifacts, and final reporting must not claim remote/worktree verification.

## Completion criteria

- Requirements and architecture artifacts are complete and consistent.
- Implementation meets the approved architecture with proportional tests.
- Relevant tests, health checks, routing checks, and the controlled demonstration have observable results.
- Independent QA and review pass with no unresolved high-severity findings.
- Documentation and final release report are current and honest about blockers.
