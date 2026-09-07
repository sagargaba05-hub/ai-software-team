# Product Definition

## Product

Reusable Local-First AI Software Team for VS Code.

## Product objective

Enable a user to provide a concrete business or software requirement and have a reusable agent team plan, implement, test, independently review, secure, document, and quality-gate the resulting repository changes with minimal routine intervention.

The system separates two decisions:

- roles decide what work is required;
- routing decides which model performs that work.

Routine work is local-first. Qwen3-Coder 30B is the primary implementation model, GPT-OSS 20B is the independent reviewer and reasoning model, and Codex/GPT is a bounded paid escalation route. OmniRoute is the replaceable OpenAI-compatible routing layer, not the workflow authority.

## Primary users

- A product owner or developer who can state a desired outcome but should not need to manually assign agents or models.
- A maintainer who needs observable workflow state, evidence for completion, bounded paid-model use, and safe recovery after interruption.
- A future project team that wants to initialize an existing repository without overwriting useful documentation or forcing a language-specific template.

## User promise

Given a valid repository and a concrete objective, the system will:

1. inspect the repository and applicable project rules;
2. define product requirements and an implementation approach;
3. select only the specialist roles the work requires;
4. route routine coding to Qwen and independent review/reasoning to GPT-OSS;
5. test changes proportionally and run security review when risk triggers apply;
6. permit no more than three meaningful local repair/review cycles before a qualifying escalation decision;
7. use Codex only when an explicit premium escalation condition is met and within configured limits;
8. keep project documentation and persistent workflow state current;
9. refuse final approval unless the evidence-based quality gate passes; and
10. report failures, skipped checks, and remaining blockers honestly.

## In scope

- A reusable supervisor and persistent workflow for feature, bugfix, refactor, review-only, and security-sensitive work.
- Clear responsibilities, entry conditions, outputs, preferred and fallback routing, escalation conditions, and completion criteria for Team Lead, Architect, Developer, Debugger, Reviewer, Tester, Security Reviewer, Documentation Engineer, and Final Quality Gate.
- Normal and premium routing policies that remain distinct from role selection.
- Qwen3-Coder 30B and GPT-OSS 20B access through OmniRoute, with provider details hidden behind an OpenAI-compatible client boundary.
- Explicit, bounded Codex escalation with an off switch, per-run limit, reason, prior-attempt evidence, and outcome logging.
- Repository-aware context minimisation, sensitive-file exclusion, and provider-failure fallback behavior.
- Project bootstrap that preserves existing files, detects relevant project commands and risks where evidence allows, and creates only missing useful artifacts.
- Human-readable and machine-readable health/status output sufficient to diagnose local runtime, model, routing, skills, credentials configuration, and repository access.
- Lightweight usage and escalation records that exclude secrets and sensitive source content.
- VS Code/Continue integration through a repository-explicit MCP interface, while keeping the CLI independently usable.
- Automated tests plus a controlled end-to-end demonstration of coding, review, escalation decision, and non-escalation behavior.
- Documentation and a final release report grounded only in observed results.

## Explicit exclusions

- Automatic push, merge, deployment, history rewriting, force-push, branch deletion, destructive migration, or acceptance on the user's behalf.
- Mandatory paid providers other than the explicitly approved and disableable Codex escalation route.
- A dependency on optional free-cloud providers; provider availability is not assumed to be stable.
- Claude, paid OpenRouter, Gemini Pro, or any other unapproved paid API as a required component.
- Kubernetes, unnecessary containers, message queues, orchestration-only databases, expensive observability platforms, or multiple competing VS Code agent extensions.
- Sending full repositories or full conversation histories to every role by default.
- Hiding failed checks, fabricating model availability, treating generated code as evidence of correctness, or weakening a gate to obtain a passing result.
- Reinstalling healthy tools or models solely to conform to a preferred setup.
- Assuming a target project's language, framework, build system, or documentation structure without repository evidence.

## Product principles

### Local-first and cost-aware

Local models perform routine work. Optional free providers may assist only after current classification. Paid escalation is automatic only under approved conditions, bounded, logged, and disableable.

### Independent evidence

Important implementation is not approved solely by its authoring model. Review, relevant executable tests, security checks when triggered, documentation completion, and the final gate produce observable evidence.

### No gate bypasses

A failed or unavailable required check remains failed or blocked. The system may use an approved fallback, retry within policy, or escalate when eligible, but it must not relabel, skip, mock, or weaken a mandatory gate and then claim completion. Simulated components are acceptable only in an explicitly labelled controlled demonstration and never as proof of live provider availability.

### Minimum necessary context and complexity

Each role receives the smallest useful repository context. The implementation should prefer a compact, replaceable architecture and reuse existing healthy installations and project conventions.

### Safe autonomy

Routine technical decisions are resolved from repository evidence, approved policy, and the agent workflow. User input is required only for a genuine business decision, missing authorization or credentials, or materially ambiguous product intent.

## Success measures

The product is successful when all of the following are evidenced:

- A new or existing repository can be initialized without overwriting useful existing documentation or production code.
- A controlled run routes implementation to Qwen and independent review to GPT-OSS through OmniRoute.
- A qualifying escalation decision is observable, bounded, and logged; an ordinary task demonstrably does not call Codex.
- Failed QA or review returns to the correct repair owner and cannot loop indefinitely.
- Security-sensitive objectives automatically receive security review before release.
- Interrupted work can be inspected and resumed from persisted state.
- The final gate cannot approve unless requirements, tests, review, security when applicable, documentation, secret hygiene, and unresolved-issue reporting are satisfied.
- A maintainer can run one documented health command and identify unavailable required components without secrets appearing in output.

## Current repository status

This repository already contains a Python CLI, LangGraph supervisor, state persistence, role-skill loader, OmniRoute-compatible client, Codex executable integration, MCP server, bootstrap logic, health checks, tests, and operating documentation. These are implementation inputs, not automatic proof that every requirement below is met.

The repository is currently an uncommitted Git repository without an origin or verifiable base branch. The user explicitly selected this open folder as the implementation target. Work therefore proceeds in place as the smallest viable alternative, without claiming isolated-worktree, remote, merge, push, or deployment verification.

## Product completion boundary

Release approval means the local framework and its controlled demonstration meet `docs/REQUIREMENTS.md`, with independent QA and review evidence and no unresolved blocker or high-severity finding. It does not mean a downstream user project has been deployed, merged, or accepted by a human product owner.
