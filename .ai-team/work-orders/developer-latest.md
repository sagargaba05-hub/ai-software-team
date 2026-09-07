# Developer Work Order Evidence

Status: BLOCKED_QWEN_ANALYSIS

- Required route: `ollama/qwen3-coder:30b` through OmniRoute.
- Successful identity probe: `2026-09-06T09:07:05.338Z`; requested `ollama/qwen3-coder:30b`; returned `qwen3-coder:30b`; HTTP 200; OmniRoute request `1788685605718-9a5a13`.
- Substantive analysis attempts: rejected as evidence because OmniRoute returned `gpt-oss:20b` despite the requested Qwen route, or returned a bounded 504 before response headers.
- Router mitigation applied: `OMNIROUTE_DIRECT_HEADERS_TIMEOUT_MS=300000` in the repository launcher; the substantive request was still misrouted.
- Codex calls: zero.

Implementation continued from the approved `docs/TASKS.md` contract with engineering judgment. It must not be described as Qwen-led until a substantive response returns Qwen route identity.

## Implementation validation

- `python -m pytest -q`: PASS, 68 tests.
- `python -m compileall -q src tests`: PASS.
- `python -m pip check`: PASS, no broken requirements.
- `python -m ai_team doctor`: PASS after authenticated localhost launcher and route-probe fixes; Qwen and GPT-OSS identities and non-empty outputs verified.
- `python -m ai_team demo .`: PASS; live Qwen coding route, live GPT-OSS independent route, subprocess-impossible simulated premium decision, zero routine Codex activity, and disposable cleanup.
- Windows path with spaces and Unicode punctuation: first bootstrap created 21 artifacts, second created 0, existing README hash remained unchanged, dry-run exited 1 with honest `BLOCKED` because simulated evidence cannot satisfy the live gate.
- Ruff was not installed in the project environment and was not installed implicitly.
