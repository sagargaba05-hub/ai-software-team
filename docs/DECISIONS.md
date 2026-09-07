# Architecture Decisions

## ADR-001: Evolve the existing local Python architecture

- **Status:** Accepted
- **Decision:** Retain the Python CLI, LangGraph state machine, OpenAI-compatible model boundary, reusable role skills, project-local SQLite, and stdio MCP bridge. Add focused policy/evidence seams only where required for testability.
- **Reason:** These components already implement useful portions of the product. Replacing them would add risk and complexity without satisfying an unmet requirement.
- **Consequences:** Existing documented commands remain compatible. No queue, container, web UI, orchestration SaaS, mandatory cloud provider, or additional database is introduced.

## ADR-002: Select roles before selecting models

- **Status:** Accepted
- **Decision:** Produce a provider-neutral `WorkProfile` and `RolePlan`, map each role to a capability, then independently map the capability to an eligible route.
- **Reason:** Requirements R-02 and R-03 demand task-based specialist selection and transport-independent workflow logic.
- **Consequences:** Feature, bugfix, refactor, review-only, and security-sensitive work use proportional paths. Debugger and Security Reviewer become explicit recorded stages. Physical model/provider identifiers remain configurable.

## ADR-003: Keep normal and premium routes disjoint

- **Status:** Accepted
- **Decision:** Normal coding uses Qwen3-Coder 30B and independent reasoning/review uses GPT-OSS 20B through OmniRoute. Codex is reachable only through an explicit `PremiumDecision` satisfying an approved condition, enabled policy, and a reserved per-run call slot.
- **Reason:** Executable discovery and output-quality preference are not valid escalation triggers. Paid calls must be bounded and auditable.
- **Consequences:** Optional provider failure falls back only to an eligible local route. Premium failure or disabled/over-limit state is visible and may block the run. A successful premium response must still pass normal evidence gates.

## ADR-004: Make evidence structured and release deterministic

- **Status:** Accepted
- **Decision:** Persist typed stage/test/review/security/route evidence and compute the release outcome in code. Model prose may explain results but cannot set the gate outcome by writing `STATUS: PASS`.
- **Reason:** Current prose parsing cannot prove tests ran, preserve independent findings, or prevent stale/malformed output from advancing.
- **Consequences:** Missing evidence fails closed. Review severities and owners are machine-checkable. Release reports are regenerated from the current run and distinguish approved, failed, and blocked outcomes.

## ADR-005: Count meaningful repair cycles per unresolved finding

- **Status:** Accepted
- **Decision:** Allow at most three repair attempts after an initial failed check for a stable finding fingerprint. Keep Tester and Reviewer counters/results independent and require fresh checks after every significant repair.
- **Reason:** The current shared counter and `<= maximum` transition permit a fourth repair and allow unrelated results to interfere.
- **Consequences:** The third failed repair check evaluates premium policy; no fourth local repair begins. Identical retries without changed work/evidence do not reset the count.

## ADR-006: Use project-local versioned state and append-only audit metadata

- **Status:** Accepted
- **Decision:** Continue using `.ai-team/state.sqlite3`, adding schema/run identity and a single-active-run lease. Keep an atomic JSON mirror and append redacted usage/escalation JSONL records keyed by run ID.
- **Reason:** SQLite is sufficient for local durability and concurrency without a new service. Existing overwritten Markdown artifacts alone are not adequate audit history.
- **Consequences:** Resume preserves the exact plan, evidence, and counters. Incompatible/corrupt state is diagnosed without destructive recovery. Logs contain metadata/evidence references, not prompts, source, or secrets.

## ADR-007: Treat live health, simulation, and test evidence as different classes

- **Status:** Accepted
- **Decision:** Doctor performs typed component checks and separate controlled route probes. The demo records live Qwen and GPT-OSS assertions separately from fake control-flow tests and a hard-disabled simulated Codex decision.
- **Reason:** A listening port, generic HTTP response, `/models`, dry-run, or fake client cannot prove correct live routing.
- **Consequences:** Unavailable live dependencies produce `BLOCKED` rather than a fabricated pass. Codex-disabled mode does not fail health solely because Codex is absent.

## ADR-008: Preserve user work in the current in-place repository

- **Status:** Accepted with limitation
- **Decision:** Work in the user-confirmed open folder, include staged/unstaged/untracked scope, and report missing origin/base as an isolation limitation. Do not invent a remote, baseline commit, or worktree.
- **Reason:** The user authorized in-place completion and clarified that “no bypasses” means no requirement or verification shortcuts, not forced repository infrastructure.
- **Consequences:** Local implementation and tests may proceed. Isolated-worktree, upstream comparison, push, merge, deployment, and remote delivery cannot be claimed.

## ADR-009: Bootstrap detects facts but does not execute or overwrite

- **Status:** Accepted
- **Decision:** Bootstrap creates only missing contracts and records bounded evidence-based stack, candidate-command, security-area, and Git facts. It leaves uncertain values unresolved and existing useful files byte-for-byte intact.
- **Reason:** Reusable initialization must be language-neutral, idempotent, and safe for established repositories.
- **Consequences:** Candidate commands are verified later by Tester/doctor. A second bootstrap produces no semantic change other than explicitly documented timestamps.
