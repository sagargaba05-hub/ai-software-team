# Security

## Continue and local tool boundary

- OmniRoute reasoning metadata is stripped before streamed model output is shown in Continue.
- Repository reading excludes secrets, binary files, dependencies, caches, generated output, and AI-team runtime logs.
- Durable context rejects credential-like values and must contain only user-confirmed non-secret facts.
- Local tools run without a shell from the active workspace or a safe subdirectory.
- Only checked-in Python/Node files, pytest, npm test/run scripts, and explicitly read-only Git commands are exposed automatically.
- Inline interpreter code, path escape, mutating Git operations, arbitrary commands, pushes, merges, and deployments are blocked.
- GitHub status reports account and repository metadata but never returns tokens.

These controls reduce accidental cross-project and credential exposure. They do not grant unattended deployment authority.
