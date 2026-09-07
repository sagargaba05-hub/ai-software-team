# Architecture

Status: Approved implementation contract for the current work order.

## Architecture objective

Evolve the existing Python CLI, LangGraph supervisor, OpenAI-compatible model client, reusable role-skill loader, and project-local SQLite state into the smallest system that satisfies `docs/REQUIREMENTS.md`. OmniRoute remains replaceable model transport; it does not choose workflow stages, approve evidence, or own retry and escalation policy.

The implementation must preserve documented CLI and MCP entry points, user files, and useful current modules. It must not introduce a web service, queue, container, additional database, mandatory cloud provider, or second IDE agent extension.

## Trust boundaries and component ownership

| Component | Responsibility and required change | Must not do |
|---|---|---|
| `cli.py` | Validate explicit repositories/objectives; expose `doctor`, `init`, `run`, `status`, `resume`, `dry-run`, and a controlled `demo`; return distinct successful, failed, blocked, and invalid-input exits. | Infer another repository, turn a blocked run into success, or describe dry-run as live evidence. |
| `mcp_server.py` | Keep an explicit absolute repository or `.` contract; expose the same core actions including doctor; apply finite timeout; return workflow `FAIL`/`BLOCKED` output as a normal tool result and reserve transport errors for execution failure. | Invoke through a shell, swallow nonzero workflow outcomes, or select a workspace implicitly. |
| `supervisor.py` | Classify work, select required roles, execute state transitions, enforce meaningful repair cycles and escalation eligibility, and assemble structured gate inputs. | Route based on provider response fields, perform specialist work itself, or approve release. |
| `workflow.py` or focused additions to `supervisor.py` | Hold pure task-classification, risk-trigger, transition, retry, and gate functions. Split only if it makes these policies independently testable. | Duplicate model routing or skill text. |
| `skills.py` / `constants.py` | Load and structurally validate the nine authoritative role contracts: Orchestrator, Architect, Developer, Debugger, Reviewer, Tester, Security Reviewer, Documentation, and Final Quality Gate. Validate each contract's responsibility, entry conditions, output, preferred route, fallback, escalation conditions, and completion criteria. | Embed divergent role prompts in Python. |
| `config.py` | Hold finite context, request timeout/retry, MCP timeout, three-cycle, premium-call, provider-eligibility, and demo bounds; map roles to capabilities and capabilities to routes separately. | Let provider names leak into workflow transitions. |
| `models.py` | Implement bounded normal-route calls through the configured OmniRoute OpenAI-compatible endpoint, validate non-empty responses, classify failures, and expose a separately authorized premium adapter. | Retry indefinitely, silently switch to a paid provider, or invoke Codex from executable availability alone. |
| `provider_registry.py` or focused additions to `models.py` | Discover configured providers and record evidence-based `LOCAL`, `FREE`, `FREE-TIER`, `PAID`, or `UNKNOWN` classification plus eligibility. | Treat an unverified or stale price label as free. |
| `executor.py` | Build role-scoped context, invoke the selected capability, validate structured results, safely apply authorized patches, run/collect executable commands for Tester, and persist evidence. | Give write authority to review-only, Security, or Final Gate; accept prose `STATUS` as test evidence. |
| `repository.py` | Inspect bounded relevant files; include staged, unstaged, and untracked work in change scope; exclude secrets, generated/vendor/cache data, VCS internals, and runtime data such as `omniroute-data`; detect Git isolation limitations. | Discard user changes or claim a base diff when no base exists. |
| `documents.py` | Idempotently create only missing artifacts and produce evidence-based onboarding facts for detected stack, candidate commands, and security areas, leaving unknowns explicit. | Modify an existing useful file during bootstrap or guess a framework/command. |
| `state_store.py` | Persist versioned run state and append-only evidence under the target `.ai-team`; provide transactional single-active-run ownership and atomic human-readable mirror writes. | Reuse corrupt/incompatible state or let concurrent starts overwrite one another. |
| `audit.py` (new, small) | Append redacted JSONL usage, escalation, stage, test, review, security, and gate records keyed by run ID. | Store prompts, source content, credentials, or exception strings before redaction. |
| `doctor.py` | Report required/optional status for host tools, write access, skills, Ollama/models, OmniRoute HTTP/API, controlled routes, provider classification, and conditional Codex readiness in human and JSON forms. | Treat any HTTP response below 500, a listener, or `/models` alone as routed inference success. |
| `demo.py` (new, small) | Run a bounded disposable controlled task: live Qwen coding route, live GPT-OSS independent review route, simulated eligible premium decision with invocation disabled, and routine zero-Codex assertion. | Modify unrelated production behavior or let fake evidence satisfy a live criterion. |

New modules above are permitted seams, not mandatory abstractions. The Developer may keep logic in an existing module when the same interfaces, isolation, and tests remain clear.

## Core domain contracts

### Work classification and role plan

`WorkProfile` is derived before model selection from objective, repository evidence, and changed-area risk signals:

- `kind`: `FEATURE | BUGFIX | REFACTOR | REVIEW_ONLY`
- `significance`: `TRIVIAL | SIGNIFICANT`
- `security_required`: Boolean plus deterministic trigger reasons
- `architecture_required`: Boolean plus reason
- `documentation_assessment_required`: always true before gate
- `candidate_commands`: evidence-backed test/build/lint commands only

`RolePlan` is an ordered list of role/capability requests. It contains no provider response fields or physical model decisions. Required minimum plans are:

| Work | Required route |
|---|---|
| Feature | inspect/bootstrap -> Orchestrator plan -> Architect when the change is meaningful -> Developer -> Tester -> Reviewer for significant work -> Security Reviewer when triggered -> Documentation -> Final Gate |
| Bugfix | inspect/bootstrap -> Orchestrator plan -> Debugger (reproduction/cause/affected area) -> Developer -> Tester including regression evidence where practical -> Reviewer -> Security Reviewer when triggered -> Documentation -> Final Gate |
| Refactor | inspect/bootstrap -> Orchestrator plan -> Developer/refactor implementation -> Tester proving preserved behavior -> Reviewer -> Security Reviewer when triggered -> Documentation -> Final Gate |
| Review-only | inspect -> Reviewer and Security Reviewer when triggered -> Final Gate/report; production mutation is forbidden unless a separately authorized remediation objective is created |
| Security-sensitive | the applicable plan above plus an explicit recorded Security Reviewer stage before Documentation/Final Gate |

Product analysis may update approved requirements only when the objective needs clarification into a delivery contract. It is not a mandatory model call for every small downstream task. Refactoring is likewise selected when warranted, not an unconditional stage. Debugger and Security Reviewer are explicit role results with their own artifacts and state; their responsibilities cannot be satisfied by a sentence in another role's prompt.

### Role-to-capability and capability-to-route interfaces

The supervisor asks `role_policy.capability_for(role, work_profile)` for a logical capability such as `CODING`, `REASONING`, `INDEPENDENT_REVIEW`, or `PREMIUM_REASONING`. A separate router asks `route_policy.select(capability, provider_registry, run_policy)` for a route decision:

```text
RoleRequest(run_id, task_id, role, capability, context_refs, attempt)
  -> RouteDecision(route_type, model_id, provider_id, reason, fallback_chain)
  -> ModelResult(result_state, content, provider_evidence, failure_class)
```

Default normal mappings are:

- `CODING`: `ollama/qwen3-coder:30b` through OmniRoute; used for implementation, bug fixes, refactoring, test creation, and allowed documentation edits.
- `REASONING` and `INDEPENDENT_REVIEW`: `ollama/gpt-oss:20b` through OmniRoute; used for architecture, debugging/reasoning, reviewer, security review, and final reasoning. The significant-work reviewer must be independent of the authoring model.
- Optional providers are not in the core chain. `LOCAL` and currently evidenced `FREE` may be enabled; `FREE-TIER` requires an explicit policy opt-in and current no-billing/limit evidence; `PAID` and `UNKNOWN` are disabled. Optional discovery failure falls back to the local core and is recorded.

Provider/model IDs remain configuration, so replacing OmniRoute with a compatible gateway changes the client/configuration boundary, not the role graph.

### Result and evidence states

Every selected stage persists a structured `StageResult` with `run_id`, role, attempt, started/ended timestamps, `PASS | FAIL | BLOCKED | NOT_REQUIRED`, artifact paths, evidence references, findings, remediation owner, and route evidence when a model was called. Missing or malformed output becomes `FAIL` or `BLOCKED`; it never advances as success.

Tester evidence records the exact argument-list command, working directory, exit code, bounded/redacted output location, timestamp, and requirement IDs covered. Reviewer findings use `BLOCKER | HIGH | MEDIUM | LOW | SUGGESTION` and name `architect | developer` as owner. Security records either a completed review or `NOT_REQUIRED` with deterministic reasons. Documentation records `COMPLETE` or a justified `NO_CHANGE`; an absent assessment is not `NO_CHANGE`.

## Normal repair route

A meaningful failed cycle is one completed repair followed by fresh executable Tester and, when applicable, independent Reviewer evidence for the same unresolved finding fingerprint. Identical retries without a changed patch/evidence fingerprint do not reset or create a new cycle; they fail visibly.

`MAX_LOCAL_REWORK_LOOPS=3` means at most three repair attempts after the first failure, with checks performed after each repair. The transition condition is `failed_cycles < 3 -> repair owner`; once the third repair check still fails, no fourth repair starts and premium eligibility is evaluated. QA and review findings have separate counters/fingerprints so a Reviewer failure cannot consume, reset, or erase Tester state. A Tester failure routes to Developer; an architecture-owned Reviewer finding routes to Architect, then Developer as needed; all significant remediation returns through Tester and independent Reviewer. Passing one gate never clears another gate's open findings.

## Premium route

Premium routing is a distinct policy path, not a fallback for quality preference. `PremiumDecision` must name exactly one approved R-05 condition, impact, local attempt/disagreement evidence references, enabled state, per-run limit position, and `SELECTED | NOT_ELIGIBLE | DISABLED | LIMIT_REACHED` outcome.

Only `SELECTED`, `CODEX_ENABLED=true`, `calls_used < limit`, and a non-simulation request may reach `CodexEscalator`. The call slot is reserved and logged before process invocation; attempted calls count even on timeout/nonzero exit. Arguments use a fixed list, input and output are bounded/redacted, and execution has a finite timeout. Success returns to the owning repair stage and must pass fresh Tester/Reviewer/Security gates; it never directly approves release. Disabled, unavailable, over-limit, or unresolved premium work ends `BLOCKED` or `FAIL` with evidence. A simulation executes policy and logging while hard-disabling the subprocess.

## End-to-end data flow

```text
CLI / MCP explicit repository + objective
  -> repository validation and single-run lease
  -> bounded inspection + Git/isolation facts + bootstrap/onboarding
  -> WorkProfile -> RolePlan
  -> RoleRequest -> capability mapping -> route policy -> OmniRoute/model
  -> validated StageResult + append-only audit record + state transaction
  -> authorized patch validation/application or executable test collection
  -> failure fingerprint -> repair owner / bounded cycle / PremiumDecision
  -> Documentation assessment
  -> deterministic Final Gate over current evidence
  -> RELEASE_APPROVED | FAIL | BLOCKED and release report
```

State transitions save the next stage only after the current result and audit reference are durable. Resume uses the persisted run ID, plan, completed results, counters, and active lease; it does not rebuild a new plan or rerun completed stages unless an explicit invalidation reason is recorded.

## Persistence and migration

Continue using one project-local `.ai-team/state.sqlite3`; add a schema version, immutable run ID, active-run lease/owner, role plan, per-finding cycle records, premium reservations, stage result references, and timestamps. Use a SQLite transaction for state/lease changes and an atomic temp-file replace for `state.json`. Append audit events to `.ai-team/logs/usage.jsonl` and `.ai-team/logs/escalations.jsonl` with a lock or transaction-backed monotonic sequence so earlier evidence is preserved.

Existing unversioned state is never guessed into the new schema. A compatible migration may map known fields and retain the original payload as an artifact; otherwise status/resume returns a non-destructive incompatibility diagnostic. Bootstrap may create missing directories and metadata but must not overwrite existing documentation, production code, or state. No application-data or destructive Git migration is part of this work.

## Repository, patch, and context safety

- Resolve and validate the target directory before creating state; CLI and MCP reject empty objectives, files, nonexistent targets, and ambiguous relative paths.
- Record Git status, head/base/origin when available. Include tracked staged/unstaged changes and untracked text files within bounds. With no commit/origin, report the exact isolation limitation and compare against the captured task manifest/current work scope; do not claim remote or worktree verification.
- Use case-insensitive secret-path rules covering environment files, credentials, tokens, private keys/certificates, and nested variants. Exclude generated, dependency, cache, binary, VCS, logs, database/runtime, and `omniroute-data` paths from model context and patches.
- A role receives referenced requirements/findings and only relevant bounded files/diffs. Logs store metadata and artifact hashes/paths, not full prompts or source.
- Only explicitly mutating roles may emit patches. Reject multiple/empty-malformed/out-of-scope/secret/generated patches; perform full validation before a single apply so a failed validation cannot partially modify the repository.
- Subprocesses use fixed argument arrays, explicit working directories, finite timeouts, bounded output, and no shell. Redact secrets from diagnostics at the boundary.

## Bootstrap and health contracts

Bootstrap is idempotent and evidence-driven. It creates only missing AI-team/document contracts, inventories within bounds, and records detected languages/frameworks, candidate build/test/lint commands, security-relevant areas, Git limitations, and unresolved values in a dedicated onboarding artifact. Detection never executes project commands and never overwrites useful files; command execution belongs to controlled test/health work.

Doctor emits the same typed checks in human and JSON form: check ID, `PASS | FAIL | AVAILABLE | UNAVAILABLE | CONFIGURED | NOT_CONFIGURED`, required flag, safe detail, and evidence timestamp. Required checks are Git, supported Python, role-contract validity, target write access, Ollama/compatible runtime, both local models, OmniRoute HTTP/API readiness, and controlled Qwen/GPT-OSS route checks for a live demonstrated path. Optional-provider discovery and conditional Codex configuration/authentication are separate. Codex absence does not fail overall health when disabled. Network errors, unauthorized responses, wrong route/model identity, empty inference, and malformed responses remain distinct failures; no credential value is rendered.

## Controlled demonstration

The demo operates in a disposable repository/artifact scope with strict time, context, output, repair, and premium bounds. It records four independently evaluated assertions:

1. a live coding request travels through OmniRoute and produces observable Qwen3-Coder 30B route identity;
2. a live independent review request travels through OmniRoute and produces observable GPT-OSS 20B route identity;
3. a labelled simulation produces an eligible premium decision while the Codex subprocess is impossible to invoke; and
4. a routine path has zero premium selections, reservations, attempts, and calls.

Fake clients may test control flow but are marked `SIMULATED` and cannot satisfy assertions 1 or 2. An unavailable required runtime yields `BLOCKED` for that live assertion and prevents release approval.

## Deterministic final quality gate

The Final Gate consumes structured current-run evidence rather than a model's claimed `STATUS`. Release is approved only when all applicable requirements and architecture checks are accounted for, implementation roles completed, required commands exited successfully, independent review passed with no open `BLOCKER`/`HIGH`, the security decision is present and passed when triggered, documentation is `COMPLETE` or justified `NO_CHANGE`, secret hygiene/change-scope checks pass, no required health/demo check for the demonstrated path failed, and no provider/escalation failure remains open.

The gate outputs `RELEASE_APPROVED`, `FAIL`, or `BLOCKED`; lists every check and evidence reference; and explicitly names `NOT_REQUIRED`/skipped items with reasons. A reasoning model may produce a narrative summary but cannot change the deterministic outcome. The release report is regenerated from the current run only, so stale reports cannot unlock or represent a new run.

## Verification boundaries

Unit tests must cover role/capability separation, work classification, security triggers, every transition, exactly-three repair exhaustion, separate QA/review fingerprints, premium eligibility/disabled/limit/simulation behavior, provider classification, redaction, path/context exclusions, patch scope/atomic validation, schema incompatibility, concurrency lease, resume, and negative final-gate cases.

Integration tests must cover CLI/MCP validation and exit behavior, non-destructive/idempotent bootstrap with detected/unknown facts, append-preserving logs, staged/unstaged/untracked scope, provider timeout/rate-limit/empty/malformed responses, and a complete fake-client workflow explicitly labelled simulated. Live verification must separately run doctor route probes and the controlled demonstration. Test success proves code behavior only; operational readiness additionally requires current live model/routing evidence and independent QA/security/review artifacts.

## Implementation boundaries

- Preserve backward-compatible documented commands and the existing local-first model identities.
- Do not modify global skill contracts except through the separately assigned role-contract task; consume them as the single source of role behavior.
- Do not push, merge, deploy, rewrite Git history, discard user changes, delete branches, reinstall healthy tools/models, or perform destructive migrations.
- Do not weaken, skip, mock, or relabel a required gate to obtain release approval.
- The current repository has no origin or base commit. In-place implementation is authorized, but isolated-worktree, upstream-diff, remote-delivery, and deployment verification remain unclaimed.
