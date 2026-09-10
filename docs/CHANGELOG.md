# Changelog

## 2026-09-07

- Added exact VS Code workspace self-identification for the global MCP server.
- Added objective-aware safe repository inventory, file search, and file reading.
- Added durable, secret-rejecting project context.
- Added bounded local test/build execution and read-only GitHub status.
- Configured Continue to use complete responses and OmniRoute to remove provider reasoning metadata before chat output.
- Upgraded workflow persistence to schema v3 with a pending-stage cursor, repair-cycle records, and append-only stage results.
- Corrected local retry semantics to allow three repairs and fresh rechecks after the initial failure, with no fourth repair.
- Added post-change security classification that latches Security Reviewer into the active plan.
- Made Final Gate deterministic and dependent on structured current-run evidence.
- Bound nested model audit events to the active run and expanded credential redaction inside arbitrary strings.
- Hardened model patch validation across old/new headers and rename/copy metadata before `git apply`.
- Made the global MCP execution timeout validate `MCP_TIMEOUT_SECONDS` without reading project `.env` files.
