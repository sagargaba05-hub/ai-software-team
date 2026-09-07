# Model Routing

Roles request capabilities rather than model names. Defaults are configured in `.env`:

| Capability | Default route | Roles |
|---|---|---|
| Coding | `ollama/qwen3-coder:30b` | Developer, Refactor, QA, Documentation |
| Reasoning | `ollama/gpt-oss:20b` | Product, Architect |
| Independent review | `ollama/gpt-oss:20b` | Reviewer, Release |

All live local-agent requests use `OMNIROUTE_BASE_URL`. Optional providers can be added inside OmniRoute without changing workflow code. Do not commit API keys.

The client adds an internal `AI_TEAM_ROUTE_CODING` or `AI_TEAM_ROUTE_REASONING` marker to each role request. OmniRoute's task-aware router gives these markers deterministic priority, while ordinary Continue requests are classified from the user's latest message. Continue therefore exposes one virtual model and never asks the user to choose a physical model.
