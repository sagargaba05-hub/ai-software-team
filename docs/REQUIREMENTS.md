# Product Requirements

## Status and authority

These requirements translate `.ai-team/TEAM_BRIEF.md` and the approved master setup specification into a testable delivery contract. Repository evidence may determine implementation details, but it may not weaken a `MUST` requirement. Existing code is not considered verified until the relevant acceptance evidence exists.

Priority terms:

- `MUST`: required for release approval.
- `SHOULD`: expected unless a documented repository constraint justifies a smaller equivalent.
- `MAY`: optional and must not become a core dependency.

## Functional requirements and acceptance criteria

### R-01: Requirement-driven orchestration

The system MUST accept a target repository and concrete objective, inspect repository rules and current state, and select the required workflow roles without requiring the user to assign models or agents manually.

Acceptance criteria:

- The CLI and MCP entry points reject an empty objective and a nonexistent target repository with a clear error.
- The target repository is explicit; an omitted or ambiguous relative path cannot silently select another project.
- A normal run records its objective, current stage, completion state, retry count, and premium-call count in persistent project-local state.
- `status` reports the last persisted state without starting or modifying a workflow.
- `resume` continues an interrupted valid run and fails clearly when no resumable state exists.

### R-02: Role contract and separation

The framework MUST provide the following responsibilities: Team Lead/Orchestrator, Solution Architect, Developer, Debugger, Code Reviewer, Test Engineer, Security Reviewer, Documentation Engineer, and Final Quality Gate. Each role contract MUST define responsibility, entry conditions, expected output, preferred route, fallback route, escalation conditions, and completion criteria.

Acceptance criteria:

- An automated validation identifies a missing, unreadable, or structurally incomplete required role contract.
- Role instructions are loaded from the declared reusable skill source rather than duplicated as divergent hard-coded prompts.
- The orchestrator coordinates work but does not serve as the default implementer, reviewer, tester, or final approver.
- Debugger and Security Reviewer responsibilities are invocable as explicit workflow stages or explicit subflows with their own recorded result; merely mentioning them inside another role does not satisfy this criterion.
- Project-local rules supplement global role rules, and an explicitly recorded project constraint takes precedence.

### R-03: Role selection is independent of model routing

The workflow MUST decide what role is needed separately from which model/provider serves it.

Acceptance criteria:

- Workflow transitions identify roles or capabilities and do not depend on provider-specific response fields.
- Changing an allowed model identifier or replacing the OpenAI-compatible routing gateway does not require rewriting workflow role logic.
- Tests demonstrate at least one role-to-capability mapping and one capability-to-model mapping as separate decisions.

### R-04: Normal local routing

The default normal route MUST use Qwen3-Coder 30B for implementation, refactoring, bug fixing, and test creation, and GPT-OSS 20B for independent review and reasoning. Optional providers MUST NOT be required for core operation.

Acceptance criteria:

- Defaults identify `qwen3-coder:30b` as the coding model and `gpt-oss:20b` as the review/reasoning model.
- Live role requests travel through the configured OmniRoute OpenAI-compatible base URL.
- A controlled routing check captures evidence that a coding request reached the Qwen route and an independent review request reached the GPT-OSS route.
- The authoring model is not the only reviewer of significant implementation.
- If all optional providers are disabled, the Qwen + GPT-OSS + eligible Codex workflow remains operable.

### R-05: Premium escalation policy

Codex/GPT MUST sit behind a separate premium route. It MUST NOT be used for routine CRUD, formatting, boilerplate, documentation, basic tests, ordinary code review, simple fixes, or small refactors solely for higher output quality.

A premium escalation MAY occur only when at least one recorded condition applies:

1. three meaningful local repair attempts have failed;
2. Qwen and GPT-OSS materially disagree;
3. a decision affects several critical subsystems;
4. high-risk authentication, authorization, or security architecture is involved;
5. a major irreversible data migration decision is required;
6. local models report low confidence on a high-impact decision;
7. a severe production defect cannot be reliably explained locally;
8. the estimated cost of an incorrect decision materially exceeds the bounded escalation cost; or
9. senior final reasoning is justified for a substantial high-risk milestone.

Acceptance criteria:

- Codex can be disabled globally; when disabled, an eligible escalation becomes an honest blocked result or approved non-Codex fallback, never an unlogged invocation.
- A configurable nonnegative per-run Codex-call limit is enforced before process invocation.
- Every attempted escalation records the triggering condition, relevant local attempts or disagreement evidence, configured limit position, and outcome.
- A simulated escalation-decision test exercises policy without incurring a paid call and is labelled simulated.
- A routine controlled task records zero Codex invocations.
- The presence or availability of a Codex executable alone never triggers a call.

### R-06: Bounded repair and review

The normal local repair/review process MUST stop after no more than three meaningful failed cycles for the same unresolved issue and then evaluate premium escalation policy.

Acceptance criteria:

- The cycle counter has one documented meaning and does not allow an off-by-one fourth local repair cycle.
- Repeated identical retries without new evidence do not reset the counter.
- QA findings return to Developer; architectural review findings can return to Architect; significant fixes are independently re-reviewed.
- Passing QA does not erase unresolved review findings, and passing review does not erase failed QA.
- When escalation cannot run or does not resolve the issue, the workflow ends `BLOCKED` or `FAIL`, not approved.

### R-07: Workflow coverage

The system MUST support feature, bugfix, refactor, review-only, and security-sensitive workflows with proportional stages.

Acceptance criteria:

- Feature work covers repository analysis, requirements, architecture/plan when meaningful, Qwen implementation, tests, GPT-OSS review, triggered security review, documentation, and final gate.
- Bugfix work records reproduction or equivalent evidence, likely affected components, a regression test where practical, the smallest correct fix, relevant test execution, and independent cause/fix review.
- Refactor work demonstrates preserved behavior through relevant tests and independent review.
- Review-only work cannot silently apply production changes unless a separately authorized remediation objective is created.
- Security-sensitive work cannot reach final approval without a recorded security-review result.

### R-08: Testing and independent review

Testing MUST be proportional to change risk, and significant work MUST receive independent GPT-OSS review.

Acceptance criteria:

- Existing relevant tests run before completion; missing targeted tests are added when appropriate.
- Expected behavior, failure behavior, boundary cases, and regression risk are considered and recorded.
- A required executable test failure blocks completion unless proven unrelated and explicitly documented with evidence.
- Review findings use `BLOCKER`, `HIGH`, `MEDIUM`, `LOW`, or `SUGGESTION` severity and identify a remediation owner.
- Release has no unresolved `BLOCKER` or `HIGH` finding.
- Review checks correctness, maintainability, error handling, regressions, concurrency/performance where relevant, assumptions, coverage, architecture, and obvious security defects.

### R-09: Automatic security review

Security review MUST be triggered for changes involving authentication, authorization, sessions, accounts, passwords, encryption, secrets, APIs, payments, personal information, uploads, permissions, database access, external input, command execution, infrastructure, dependencies, or exposed network services.

Acceptance criteria:

- Trigger detection is deterministic and testable from work scope or changed areas.
- The recorded review addresses secret leakage, injection, access control, insecure defaults, credential exposure, unsafe deserialization, command injection, path traversal, input validation, authentication bypass, and dependency risk where applicable.
- Complex or high-impact security design may escalate only under R-05.
- A non-security change may record `NOT_REQUIRED` with a reason; it may not silently omit the decision.

### R-10: Documentation synchronization

Documentation assessment and updates MUST occur before the final gate.

Acceptance criteria:

- Existing useful documents are updated rather than duplicated.
- README, architecture, agent guidance, changelog, contributing guidance, security guidance, and `docs/` are assessed; only useful project-specific artifacts are created.
- Commands and behavior are described as verified only when execution evidence exists.
- Architecture decisions and material behavior changes are recorded in the appropriate existing artifact.
- Empty placeholder documents do not satisfy completion.

### R-11: Reusable project bootstrap

The framework MUST initialize a new or existing repository without assuming a language or overwriting useful work.

Acceptance criteria:

- Bootstrap validates that the target directory exists.
- Existing README, agent instructions, and documentation remain byte-for-byte unchanged unless a later authorized documentation task updates them.
- Bootstrap creates only missing useful AI-team metadata and documentation contracts.
- Inspection excludes generated, dependency, cache, binary, and known secret files.
- Where repository evidence exists, onboarding records detected language/framework plus verified build, test, lint, and security-relevant areas; unknown values remain explicitly unresolved rather than guessed.
- Project-specific rules can override referenced global defaults without copying the entire global framework.
- Running bootstrap twice is idempotent apart from explicitly documented state timestamps, if any.

### R-12: Context minimisation and sensitive data handling

Each model request MUST receive only the context needed for its assigned task and MUST exclude known secrets and generated/vendor content.

Acceptance criteria:

- Context collection enforces file-count and character/size bounds.
- Known environment, credential, private-key, certificate, binary, generated, dependency, and cache paths are excluded.
- Handoffs use concise findings, paths, and persisted artifacts rather than automatically replaying the full conversation and repository.
- Model, usage, test, review, and escalation records contain no API key, password, token, private key, or unnecessary sensitive source content.
- Real credentials are loaded from ignored local configuration or platform credential storage; example configuration contains placeholders or non-secret local defaults only.

### R-13: Provider failure handling

The system MUST fail visibly and use only approved fallbacks.

Acceptance criteria:

- Timeouts, unavailable providers, malformed responses, and routing failures produce a recorded diagnostic without secret values.
- Retry behavior is finite and does not repeatedly call the same broken provider indefinitely.
- Optional free-provider failure falls back to an allowed local model when safe.
- A failed required local route cannot be silently treated as successful because a dry-run or fake client passes.
- A failed premium call remains a failed or blocked escalation and respects the call limit.

### R-14: Model and environment health check

One health-check capability MUST report Git, supported Python, role-skill validity, repository write access, Ollama or compatible runtime, Qwen3-Coder 30B, GPT-OSS 20B, OmniRoute connectivity/routing readiness, optional-provider status, and Codex configured/authenticated status without exposing secrets.

Acceptance criteria:

- Human-readable output labels each component `PASS`, `FAIL`, `AVAILABLE`, `UNAVAILABLE`, `CONFIGURED`, `NOT_CONFIGURED`, or an equally unambiguous state.
- Machine-readable output contains the same checks and distinguishes required from optional components.
- The command exits nonzero when a required component is unhealthy.
- A listening process alone is insufficient proof of OmniRoute readiness; an HTTP health/models response and a controlled routed request are separate checks.
- Codex-disabled mode does not fail overall health solely because Codex is absent or unauthenticated.
- No credential value appears in normal output, JSON output, or exception text.

### R-15: Optional free-provider discovery

The implementation MUST inspect currently configured/discoverable OmniRoute providers and classify each as `LOCAL`, `FREE`, `FREE-TIER`, `PAID`, or `UNKNOWN` from current evidence.

Acceptance criteria:

- Only `LOCAL` and `FREE` providers are automatically eligible.
- `FREE-TIER` is disabled by default unless its no-billing requirement and acceptable limit are currently evidenced and enabled by policy.
- `PAID` providers other than the approved Codex premium route are not automatically configured.
- `UNKNOWN` remains disabled.
- Discovery failure does not block the local core, but the result and fallback are reported.

### R-16: Usage and escalation logging

The system MUST create lightweight project-local records for model activity.

Acceptance criteria:

- Each model call records timestamp, project, task, agent, selected model, route type, selection reason, result, and whether escalation occurred.
- Codex records additionally include escalation reason, meaningful local attempts already performed, and final outcome.
- Records are append-safe or otherwise preserve prior run evidence and can be associated with a run.
- Secret values and sensitive source-code content are absent.
- A test demonstrates routine, review, provider-failure, and simulated-escalation records.

### R-17: Persistent state and concurrency safety

Workflow state MUST survive interruption without silently targeting the wrong run.

Acceptance criteria:

- Persisted state is stored inside the target repository's `.ai-team` area and excludes secrets.
- Writes are atomic or transactionally safe for a single active run.
- Starting a conflicting second run is rejected or isolated; it cannot corrupt the active run.
- Resume preserves completed stages and counters rather than rerunning them without an explicit reason.
- Corrupt or incompatible state produces a diagnostic and no destructive recovery.

### R-18: Git and repository safety

The system MUST preserve user work and MUST NOT push, merge, deploy, rewrite history, force-push, delete branches, discard changes, commit credentials, or perform destructive migrations as part of the standard workflow.

Acceptance criteria:

- Repository inspection and diffs exclude known secret paths.
- Patch application validates a patch before applying it and reports a failed validation without partial success.
- Existing unrelated changes survive bootstrap, run, retry, and failure scenarios.
- No workflow stage performs an external Git mutation without a separate explicit user request.
- The absence of an origin or verifiable base branch is reported as an isolation limitation, not bypassed or represented as verified.

### R-19: Final quality gate

The Final Quality Gate MUST reject completion unless all applicable requirements are satisfied with current evidence.

Acceptance criteria:

- The gate checks requirement satisfaction, architecture conformance, implementation completeness, executed relevant tests, independent review, triggered security review, documentation, secret hygiene, unnecessary files, and unresolved issues.
- Required stages have explicit states; absence is not equivalent to pass.
- No unresolved blocker, high-severity review finding, failed required test, failed required health check for the demonstrated path, or unhandled provider failure exists.
- The final report distinguishes `RELEASE_APPROVED`, `FAIL`, and `BLOCKED` and names skipped/non-applicable checks with reasons.
- Simulated evidence is labelled and cannot substitute for required live routing/model evidence.

### R-20: Controlled end-to-end demonstration

Before release, the framework MUST run a small, bounded demonstration that does not modify unrelated production behavior.

Acceptance criteria:

- The demonstration shows a coding task routed through OmniRoute to Qwen3-Coder 30B.
- Independent review of that task is routed through OmniRoute to GPT-OSS 20B.
- A simulated qualifying escalation decision records that Codex would be selected while preventing a paid invocation.
- A routine path records that Codex was not selected or called.
- Results include timestamps, route/model identities, pass/fail state, and sufficient observable output to distinguish live provider calls from fakes.
- Any unavailable live dependency makes the corresponding live criterion blocked; the demonstration is not relabelled successful.

### R-21: Operator interfaces and start command

The framework MUST remain usable through a local CLI and SHOULD expose the same core run/status/resume/doctor actions to VS Code through MCP/Continue without requiring a competing extension.

Acceptance criteria:

- Help output documents `doctor`, `init`, `run`, `status`, `resume`, and an offline dry-run or equivalent validation command.
- MCP calls require an explicit absolute repository or `.` for the current VS Code workspace.
- Long-running MCP execution has a documented finite timeout and returns nonzero workflow results without converting them into transport errors unless execution itself fails.
- The final report provides one exact, verified command to initialize and one exact, verified command to start work on a target project.

## Non-functional requirements

### NFR-01: Compatibility

- The supported host is Windows with PowerShell and Python 3.11 or newer.
- Paths containing spaces and Unicode punctuation MUST work.
- The core MUST function without Docker and without optional cloud providers.
- OmniRoute integration MUST use an OpenAI-compatible boundary so another compatible gateway can replace it with localized configuration/client changes.
- Target repositories MAY use any language or framework; bootstrap and inspection MUST not assume Python.
- The framework MUST preserve backward compatibility for documented CLI and MCP commands unless a migration note and tests accompany an intentional change.

### NFR-02: Performance and bounds

- Repository context collection, retries, local repair cycles, premium calls, provider waits, objective length, and MCP execution MUST have finite configured bounds.
- Default behavior MUST avoid ingesting the entire repository when targeted context is sufficient.
- Health checks SHOULD complete quickly enough for interactive diagnosis and use short per-service timeouts.

### NFR-03: Auditability

- Every stage result, test result, review, security decision, escalation, and release outcome MUST be attributable to a run and stored in a human-inspectable form.
- Reports MUST distinguish observed facts, simulation, assumptions, and unresolved blockers.

### NFR-04: Maintainability

- Role skills remain a single authoritative source.
- Provider/model identifiers and limits are configurable without workflow rewrites.
- Tests cover routing decisions, transition boundaries, persistence, patch safety, context exclusions, and final-gate negative cases.

## Edge cases that must be tested or explicitly handled

- Target path does not exist, is a file, contains spaces/Unicode, or is not a Git repository.
- Repository is Git-initialized but has no commits, origin, or verifiable base branch.
- Repository contains unrelated uncommitted user changes.
- Existing documentation is useful, empty, generated, read-only, or encoded unexpectedly.
- Repository contains more files or text than context bounds permit.
- Secret-like files occur at the root and in nested directories; mixed-case names and relevant suffixes are considered.
- Qwen, GPT-OSS, Ollama, OmniRoute, Codex, or a role skill is missing independently.
- OmniRoute process is listening but its API is unhealthy, unauthorized, or routes to the wrong model.
- A provider times out, rate-limits, returns empty content, returns malformed status, or disappears mid-run.
- Codex is disabled, absent, unauthenticated, over budget, or returns a nonzero result.
- QA fails exactly three times; reviewer fails after QA passes; QA and reviewer target different repair owners.
- A finding repeats without meaningful new work, and retry counters survive resume.
- Security relevance is ambiguous or introduced by a dependency/configuration change rather than source code.
- Documentation returns `NO_CHANGE`; the gate distinguishes a justified no-change from a missing documentation assessment.
- State is missing, corrupt, from an older schema, or a second run starts concurrently.
- A model emits no patch, an invalid patch, a patch outside allowed scope, or a patch touching a known secret/generated path.
- Optional free-provider classification is stale or cannot be verified.
- A dry-run passes while live dependencies are unavailable.

## Assumptions

- The user has authorized in-place implementation in `C:\Users\sagar\Desktop\AI tools\ai-software-team` and has not authorized push, merge, or deployment.
- Qwen3-Coder 30B and GPT-OSS 20B are the approved model identities even if current runtime availability still requires live verification.
- OmniRoute is already installed or can be reused if healthy; installation or replacement is justified only by evidence of absence/incompatibility.
- Codex is an approved paid escalation mechanism, but the enabled state, authentication, and budget remain operator-controlled.
- The nine reusable role responsibilities may be implemented with more than nine workflow nodes when explicit Debugger or Security stages are needed; minimizing files does not permit omitting responsibilities.
- The repository's existing Python/LangGraph/SQLite implementation may be retained when it meets these requirements; the specification does not require the suggested directory tree verbatim.

## Current compatibility constraints

- The working repository has no commit history, origin, or verifiable base branch. Isolated-worktree and remote-diff validation cannot currently be claimed. In-place work is permitted by the confirmed user instruction, but final reporting MUST retain this limitation.
- Local-model, OmniRoute, Codex authentication, and optional-provider status are environment-dependent and must be checked live near release.
- Tests using fake clients validate control flow only. They do not satisfy live model or route acceptance criteria.
- Documentation must not describe a behavior as operational merely because a configuration default or code path exists.

## Unresolved blockers and decisions

These items do not justify bypassing work that can proceed, but they block the corresponding release claims until resolved with evidence:

1. Live availability and successful inference for Qwen3-Coder 30B and GPT-OSS 20B have not yet been established in these product artifacts.
2. OmniRoute connectivity alone is insufficient; correct model routing for both required routes still needs controlled live evidence.
3. Optional provider pricing/classification must be discovered from the currently installed configuration or authoritative current evidence; historical labels are insufficient.
4. Codex enabled/authenticated state and the safe method for simulating escalation without a paid call require verification.
5. The absence of a Git origin/base means isolated worktree, upstream comparison, and remote delivery remain unavailable unless the user later supplies repository metadata. This is not a blocker to the explicitly authorized in-place local implementation.
6. Exact performance targets are not specified. The bounded defaults should be justified by interactive local use and documented; no arbitrary throughput SLA should be invented.

No unresolved item permits a mandatory test, review, security check, documentation assessment, or final quality gate to be skipped or reported as passed.
