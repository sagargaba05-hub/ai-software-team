STATUS: FAIL

# Independent QA report

Timestamp: 2026-09-06 (Australia/Sydney)

Scope: `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, the current implementation, CLI/MCP surfaces, persistent state, security boundaries, live doctor, and controlled demonstration.

## Verdict

The implementation is not release-ready. The pre-existing 68-test suite passed, and the live environment/routing checks passed, but nine new acceptance tests reproduce mandatory contract failures. One is a direct secret-file patch-safety vulnerability. In addition, the work-order evidence explicitly records that substantive Qwen analysis did not complete.

## Executed evidence

- `.\.venv\Scripts\python.exe -m pytest -q` before adding QA tests: PASS, 68 tests.
- `.\.venv\Scripts\python.exe -m pytest -q --tb=no` after adding acceptance tests: FAIL, 9 named failures; 69 other tests passed.
- `.\.venv\Scripts\python.exe -m compileall -q src tests`: PASS.
- `.\.venv\Scripts\python.exe -m pip check`: PASS, `No broken requirements found.`
- `.\.venv\Scripts\python.exe -m ai_team --help`: PASS; documents `doctor`, `init`, `run`, `status`, `resume`, `dry-run`, and `demo`.
- `.\.venv\Scripts\python.exe -m ai_team doctor --json`: PASS (exit 0). Required Git, Python 3.14.4, nine role contracts, write access, Ollama, Qwen3-Coder 30B, GPT-OSS 20B, OmniRoute API, and both controlled route probes passed. Qwen returned `qwen3-coder:30b`; reviewer returned `gpt-oss:20b`; both were nonempty. Codex was correctly optional and `NOT_CONFIGURED` because policy disables it.
- `.\.venv\Scripts\python.exe -m ai_team demo .`: PASS (exit 0). Live Qwen and GPT-OSS route assertions, simulated eligible premium decision with impossible subprocess invocation, routine zero-Codex assertion, and disposable cleanup all reported PASS.
- `tests/test_qa_acceptance_gaps.py::test_bootstrap_is_idempotent_on_windows_space_and_unicode_path`: PASS. A repository path containing spaces, an em dash, and `café` bootstrapped once, returned no changes on the second call, and preserved an odd-encoded README byte-for-byte.
- Git limitation remains accurately observable: this is an unborn `master` branch with no commit and no origin. This does not block authorized in-place work, but isolated-worktree/upstream/remote verification cannot be claimed.

## Mandatory failures

### 1. R-18 — excluded secret files can be deleted by an accepted patch (critical)

- Test: `test_patch_cannot_delete_an_excluded_secret_file`.
- Reproduction: supply a valid deletion diff whose old path is `.env` and whose `+++` target is `/dev/null`.
- Expected: full patch validation rejects every old/new/rename/copy path touching an excluded secret and leaves the tree unchanged.
- Actual: validation examines only `+++` paths and explicitly skips `/dev/null`; Git applies the patch and deletes `.env` in the temporary repository.
- Likely affected: `src/ai_team/executor.py:92-95`.

### 2. R-19 / NFR-03 — bare status strings can unlock release without structured stage evidence

- Test: `test_release_gate_requires_structured_stage_evidence`.
- Reproduction: call `evaluate_release` with matching `run_id`, `mode=LIVE`, and manually supplied PASS strings, but no stage results, timestamps, command evidence, artifacts, route evidence, or final-gate record.
- Expected: `BLOCKED`; missing structured current-run evidence is not PASS.
- Actual: `RELEASE_APPROVED`.
- Likely affected: `src/ai_team/release_gate.py:17-58`, plus supervisor initialization that pre-fills requirements, architecture, and hygiene as PASS.

### 3. R-06 — escalation occurs after only two repair attempts

- Test: `test_three_failed_repairs_are_allowed_before_escalation`.
- Reproduction: initial QA finding plus four configured failing QA responses.
- Expected: initial implementation/check, then three Developer repair + fresh Tester cycles; four Developer and four Tester calls before escalation.
- Actual: three Developer and three Tester calls. The initial finding increments the repair counter, so only two repairs occur.
- Likely affected: `src/ai_team/supervisor.py:215-261`.

### 4. R-17 — resume reruns a completed stage

- Test: `test_resume_does_not_rerun_a_completed_developer_stage`.
- Reproduction: persist a valid active refactor run at `stage=tester` with `inspect` and `developer` completed, then resume.
- Expected: continue at Tester and preserve completed work.
- Actual: Developer is invoked again before Tester.
- Likely affected: `src/ai_team/supervisor.py:202-216`.

### 5. R-02 / R-07 / R-19 — selected Final Gate stage is never recorded complete

- Test: `test_selected_final_gate_stage_is_recorded_as_completed`.
- Reproduction: run a complete offline workflow with passing fake roles.
- Expected: the selected `final_gate` stage has an explicit recorded result/completion state before terminal evaluation.
- Actual: `completed` ends with Documentation; `final_gate` is absent, and `_finish` directly evaluates the release state.
- Likely affected: `src/ai_team/supervisor.py:277-288`.

### 6. R-09 — security relevance introduced by the actual patch is missed

- Test: `test_security_trigger_is_recomputed_from_changed_areas`.
- Reproduction: use a non-security objective whose Developer patch changes `src/auth.py`.
- Expected: deterministic post-change scope detection invokes/records Security Reviewer.
- Actual: only the initial objective is checked; no Security Reviewer runs.
- Likely affected: `src/ai_team/supervisor.py:176` and the lack of a post-patch `change_scope` security decision.

### 7. R-12 / R-16 — secret assignments embedded in strings are logged verbatim

- Test: `test_audit_redacts_secret_values_embedded_in_strings`.
- Reproduction: append `password=hunter2 token=abc123 api_key=live-secret` under a non-secret key such as `result`.
- Expected: the sensitive values are absent from the JSONL record.
- Actual: all three values are written verbatim. Only secret-shaped dictionary keys and Bearer tokens are redacted.
- Likely affected: `src/ai_team/audit.py:9-24`.

### 8. R-21 / NFR-02 — MCP execution ignores the configured timeout

- Test: `test_mcp_timeout_uses_configured_bound`.
- Reproduction: configure `MCP_TIMEOUT_SECONDS=7`, invoke `_execute`, and inspect the subprocess arguments.
- Expected: timeout 7 seconds.
- Actual: timeout remains hard-coded to 14,400 seconds.
- Likely affected: `src/ai_team/mcp_server.py:52`.

### 9. R-16 / NFR-03 — normal model activity is not attributable to its run

- Test: `test_normal_run_model_activity_is_attributed_to_current_run`.
- Reproduction: execute a Supervisor run with an audited model through the current `ModelClient.generate` interface.
- Expected: every usage record contains the Supervisor's current run ID.
- Actual: usage records contain `run_id=unbound`; the executor never passes a run ID to the model boundary.
- Likely affected: `src/ai_team/models.py:18,65,98` and `src/ai_team/executor.py:77`.

## Additional contract gaps confirmed by inspection

- R-05/R-16: escalation logs set `local_attempts` from premium calls already used, not meaningful local repair attempts; later outcomes such as executable missing, timeout, nonzero exit, and returned repair result are not appended as final escalation outcomes.
- R-06/R-08: parsed structured findings are discarded by Supervisor. Open findings and independent QA/review evidence are not persisted as typed stage results, so unresolved findings cannot be reliably preserved or gated.
- R-08/R-09: a Reviewer or Security Reviewer `STATUS: PASS` is accepted without validating the required review dimensions/security checklist. The security result is prose, not a validated structured security artifact.
- R-13: provider failures are logged by the transport but are not propagated into `open_provider_failures`, so the final gate cannot reliably block on an unhandled provider failure.
- R-14: when Codex is enabled, Doctor checks executable presence only; it does not separately verify authenticated status as required.
- R-19/R-20: `run_demo` can pass independently, but no operator flow associates its current live assertions with a workflow run or changes that run's permanently initialized `health_demo_status=BLOCKED`. A normal Supervisor run therefore cannot consume the demonstrated evidence.
- R-20/NFR-03: demo details retain returned identity and a nonempty boolean but do not preserve a response ID or bounded observable task result that independently demonstrates the coding/review task was substantively performed.
- R-21: generated release reports omit the exact verified init and start commands required by the acceptance criteria.
- NFR-02: CLI objective length is unbounded even though MCP objective length is bounded; demo-specific timeout/context settings are declared but not applied by `run_demo`.

## Qwen evidence decision

`.ai-team/qwen-analysis.json` is explicitly `BLOCKED`: its identity probe succeeded, but no substantive Qwen analysis was accepted because bounded attempts were wrong-routed to GPT-OSS or timed out. The live Doctor and Demo prove current route identity and nonempty inference, so they satisfy basic route availability. They do not retroactively prove that the substantial implementation work was performed through the required Qwen Developer route. Under the Team Brief completion criteria and R-04/R-07 workflow evidence requirements, this remains a release blocker rather than a harmless limitation.

## Acceptance coverage summary

- PASS with current observable evidence: R-03 separation, default identities in R-04, provider classification policy in R-15, bootstrap preservation/idempotence portions of R-11, live health/routing portions of R-14, controlled route/demo availability portions of R-20, and CLI help/path validation portions of R-21.
- FAIL: R-02, R-05, R-06, R-08, R-09, R-12, R-13, R-16, R-17, R-18, R-19, R-21, NFR-02, and NFR-03 for the exact reasons above.
- BLOCKED from release evidence: R-04/R-07 substantive Qwen Developer participation and any release claim requiring an actual integrated live workflow.
- Not claimed: isolated worktree, upstream diff, origin synchronization, push, merge, deployment, or production acceptance.

## Required remediation order

1. Fix secret-path validation for all diff path headers before any further patch-capable live workflow.
2. Persist structured stage/findings/evidence and make the final gate fail closed on their absence.
3. Correct repair-cycle and resume transition semantics.
4. Recompute security triggers from actual changed scope and validate the security checklist.
5. Bind usage/escalation/provider evidence to the run ID and strengthen redaction/final-outcome logging.
6. Honor configured bounds, connect live Doctor/Demo evidence to the current run, then rerun the full suite and substantive Qwen Developer step.
