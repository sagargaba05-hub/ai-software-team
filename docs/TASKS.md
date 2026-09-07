# Developer Implementation Contract

Status: Ready for implementation. Tasks are ordered by dependency and mapped to the approved requirements.

## Scope and acceptance rule

Implement the smallest compatible changes described in `docs/ARCHITECTURE.md`. Production completion requires targeted automated tests plus current live evidence where the requirement calls for it. A fake client, dry-run, model-written `STATUS`, or documentation statement cannot substitute for executable/live evidence.

## Task 1: Domain contracts, configuration, and role validation

**Affected areas:** `constants.py`, `config.py`, `skills.py`, and focused domain types.

- Define `WorkProfile`, `RolePlan`, `RoleRequest`, `RouteDecision`, `StageResult`, typed findings/evidence, and terminal states without provider-dependent workflow fields.
- Map roles to capabilities separately from capabilities to routes. Keep Qwen3-Coder 30B coding and GPT-OSS 20B reasoning/review defaults.
- Add finite validated settings for context, provider attempts/timeouts, MCP timeout, three repair cycles, Codex calls/timeouts/output, and demo limits.
- Make the authoritative role set exactly cover Orchestrator, Architect, Developer, Debugger, Reviewer, Tester, Security Reviewer, Documentation, and Final Gate. Validate all required contract sections/fields and project constraint precedence.

**Tests:** missing/unreadable/incomplete contracts; separate role/capability and capability/model mapping; invalid bounds; project override precedence.

**Requirements:** R-02, R-03, R-04, NFR-02, NFR-04.

## Task 2: Safe repository scope and evidence-based bootstrap

**Affected areas:** `repository.py`, `documents.py`, onboarding artifacts.

- Validate directories before state creation and preserve existing docs/user files byte-for-byte during bootstrap.
- Make secret/generated/runtime exclusion case-insensitive and nested; exclude `omniroute-data`, databases/logs, caches, dependencies, binaries, and VCS data.
- Bound context by files and characters and select relevant files from task/artifact references.
- Represent staged, unstaged, and untracked text changes; record Git head/base/origin/cleanliness when available and explicit limitations otherwise.
- Detect repository-evidenced language/framework, candidate build/test/lint commands, and security-relevant areas without running commands or guessing. Preserve unknowns. Keep repeat bootstrap idempotent.

**Tests:** nonexistent/file/space/Unicode/non-Git/unborn Git targets; uncommitted user changes; nested mixed-case secrets; staged/unstaged/untracked scope; size/file bounds; existing/empty/read-only/odd-encoding docs; second bootstrap; detected and unresolved onboarding facts.

**Requirements:** R-01, R-10, R-11, R-12, R-18, NFR-01, NFR-02.

## Task 3: Versioned state, concurrency lease, and append-only audit

**Affected areas:** `state_store.py`, new small `audit.py`, `.ai-team` artifact layout.

- Add immutable run IDs, schema version, persisted plan/stage/results, per-finding retry state, premium reservations/counts, and timestamps.
- Enforce one active run per target with a transactional lease; allow status read-only and resume only for the matching valid run.
- Save SQLite state transactionally and replace `state.json` atomically after durable state.
- Diagnose missing/corrupt/incompatible state without destructive reset. Migrate only recognized legacy payloads and retain migration evidence.
- Append redacted run-associated model activity to `logs/usage.jsonl` and premium decisions/attempts to `logs/escalations.jsonl`. Include required metadata and exclude source/prompt/credential content.

**Tests:** conflicting starts; resume without rerun; atomicity failure; corrupt/old state; prior log preservation; routine/review/provider-failure/simulated-escalation records; redaction.

**Requirements:** R-01, R-05, R-16, R-17, NFR-03.

## Task 4: Bounded model transport and provider policy

**Affected areas:** `models.py`, optional small `provider_registry.py`, config.

- Add finite request timeout and retry policy; classify timeout, unavailable, unauthorized, rate-limit, empty, malformed, and wrong-route results without leaking credentials.
- Discover current OmniRoute providers and attach evidence-backed `LOCAL | FREE | FREE-TIER | PAID | UNKNOWN` classification and default eligibility.
- Permit automatic use of `LOCAL`/`FREE`; require explicit evidence and opt-in for `FREE-TIER`; disable `PAID` except the separate approved Codex adapter and disable `UNKNOWN`.
- Preserve the OpenAI-compatible boundary and normal Qwen/GPT-OSS route identities. Record route/model/provider evidence returned by the gateway or controlled probe.

**Tests:** finite retry count for each failure class; local fallback; optional discovery failure; all classifications/eligibility; wrong/empty model response; secret-safe diagnostics; configuration swap without workflow change.

**Requirements:** R-04, R-13, R-15, R-16, NFR-01, NFR-02.

## Task 5: Task-based supervisor and explicit specialist stages

**Affected areas:** `supervisor.py` and, only if useful, a small pure-policy module.

- Classify feature, bugfix, refactor, and review-only work and deterministically detect security triggers from objective/scope/changed areas.
- Construct a proportional `RolePlan`; invoke Debugger for bugfix cause/reproduction and Security Reviewer as a distinct stage or recorded `NOT_REQUIRED` decision.
- Stop immediately on a failed/malformed required Product, Architect, Developer, Debugger, Documentation, or other stage instead of following its success edge.
- Forbid mutation in review-only runs unless a separate authorized remediation run is created.
- Preserve completed stages/plan/counters on resume.

**Tests:** each workflow plan; every stage failure edge; ambiguous/config/dependency security triggers; non-security `NOT_REQUIRED`; review-only mutation denial; resume transition preservation.

**Requirements:** R-01, R-02, R-06, R-07, R-09, R-17.

## Task 6: Meaningful repair cycles and premium decisions

**Affected areas:** supervisor policy, `models.CodexEscalator`, audit artifacts.

- Fingerprint unresolved Tester and Reviewer findings separately; count a cycle only after a repair and fresh check.
- Permit no more than three local repair attempts for the same finding. After the third failed repair check, evaluate R-05 without starting a fourth.
- Route Tester failures to Developer and Reviewer findings to the named Architect/Developer owner; require fresh Tester and Reviewer evidence for significant remediation.
- Implement all nine approved premium triggers. Record trigger, impact, evidence references, attempts/disagreement, enabled state, limit position, selection, and outcome.
- Reserve/count a call before bounded fixed-argument subprocess invocation. A successful response returns to repair; disabled/absent/over-limit/nonzero/timeout/unresolved outcomes remain blocked/failed.
- Provide a simulation flag that evaluates and logs policy while making subprocess invocation impossible.

**Tests:** failures one through three and no fourth repair; identical retry; independent counters/open findings; each eligibility condition plus ineligible routine work; disabled/zero-limit/limit boundary; attempted-call accounting; subprocess timeout/nonzero; simulation never invokes; success re-enters gates.

**Requirements:** R-05, R-06, R-08, R-13, R-16.

## Task 7: Executable QA, review/security artifacts, and safe patch execution

**Affected areas:** `executor.py`, evidence/artifact helpers.

- Convert role outputs into validated structured results; missing/malformed required fields fail closed.
- Run evidence-backed project commands using argument lists, explicit cwd, finite timeout, bounded/redacted output, and recorded exit codes. Do not accept QA prose without execution evidence.
- Require Reviewer severities, concrete findings, evidence, and remediation owners; preserve unresolved findings across later passes.
- Record the Security Reviewer checklist/results where triggered.
- Restrict patch-capable roles and paths. Validate exactly one authorized patch completely before applying; reject secret/generated/out-of-scope changes and prevent partial application.

**Tests:** successful/failing executable checks, boundaries/regression artifact; malformed model status; review severity/owner; unresolved finding persistence; security checklist; no/empty/multiple/malformed/out-of-scope/secret patch; failed validation leaves tree unchanged.

**Requirements:** R-06, R-08, R-09, R-12, R-18, NFR-03.

## Task 8: Deterministic release gate and current report

**Affected areas:** final-gate policy, report generation, stale artifact handling.

- Compute `RELEASE_APPROVED | FAIL | BLOCKED` solely from current structured evidence covering requirements, architecture, implementation, executed tests, independent review, security decision, documentation, secret/scope hygiene, unnecessary files, health/demo path, provider/escalation failures, and unresolved issues.
- Treat absent evidence as failure/blocker; keep Tester, Reviewer, and Security results independent; reject open `BLOCKER`/`HIGH` findings.
- Allow only explicitly reasoned `NOT_REQUIRED` and documentation `NO_CHANGE` states.
- Regenerate `.ai-team/RELEASE_REPORT.md` for the current run with evidence references, simulations, limitations, rollback notes, and exact verified init/start commands. Never reuse stale approval.

**Tests:** one negative case for every gate; stale/different-run evidence; QA-pass/review-fail and inverse; missing security decision; required health/demo blocked; honest terminal/report/CLI exit mapping.

**Requirements:** R-08, R-09, R-10, R-19, NFR-03.

## Task 9: Doctor, CLI/MCP parity, and controlled demo

**Affected areas:** `doctor.py`, `cli.py`, `mcp_server.py`, new small `demo.py`, operating docs after verification.

- Emit matching human/JSON typed checks for Git, Python >=3.11, role contracts, target write access, Ollama/runtime, both required models, OmniRoute API, separate controlled Qwen/GPT-OSS routes, provider classification, and conditional Codex configuration/authentication.
- Require correct status/model identity and non-empty controlled inference; do not treat a listener or arbitrary HTTP <500 as healthy. Required unhealthy checks exit nonzero; disabled Codex is optional/not configured.
- Keep explicit repository/objective validation and finite MCP execution. Return workflow `FAIL`/`BLOCKED` as tool output, not transport failure.
- Add a bounded disposable demo with live Qwen coding, live GPT-OSS review, hard-disabled simulated eligible Codex decision, and routine zero-Codex assertion. Label every result `LIVE` or `SIMULATED` and block live criteria when unavailable.
- Keep dry-run as offline control-flow evidence only.

**Tests:** CLI help/validation/status/no-state/resume; MCP tools/repository/timeout/nonzero semantics; doctor human/JSON equivalence and required/optional exits; listener-only/unauthorized/wrong-route/empty-response failures; demo cleanup, identities, timestamps, bounds, simulation isolation, and zero premium usage.

**Requirements:** R-01, R-04, R-05, R-13, R-14, R-15, R-20, R-21, NFR-01, NFR-02.

## Task 10: Integrated verification and handoff

- Run the full automated suite and targeted failure/edge tests on Windows paths containing spaces and Unicode punctuation.
- Run idempotent bootstrap and verify unrelated existing changes remain intact.
- Run human and JSON doctor output, then the controlled live demo. Store raw safe evidence and distinguish blocked dependencies from code failures.
- Confirm usage/escalation logs contain required metadata and no credentials/source content.
- Send exact results to independent QA, then independent senior/security review; remediate without weakening gates.
- Only after both pass, synchronize documentation and generate the current final report. Do not claim origin/base/worktree, remote, push, merge, deployment, or production acceptance.

**Requirements:** all release criteria, especially R-18 through R-21 and NFR-03.

## Change boundaries

- Preserve public command names and local-first defaults unless a tested migration note is necessary.
- Avoid unrelated refactors and dependencies; standard library plus current dependencies should be sufficient.
- Do not modify real credentials, runtime databases/logs, global IDE/provider configuration, or user projects during automated tests.
- Do not reinstall healthy models/tools, invoke a paid Codex call during tests/demo, or perform external Git mutations.
- Do not mark the work complete until required automated, live, QA, review, security, documentation, and gate evidence exists; unavailable required live dependencies mean `BLOCKED`, not bypassed.
