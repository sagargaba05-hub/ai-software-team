ROLE_SKILLS = {
    "orchestrator": "ai-team-orchestrator",
    "architect": "ai-team-architect",
    "developer": "ai-team-developer",
    "debugger": "ai-team-developer",
    "reviewer": "ai-team-reviewer",
    "tester": "ai-team-qa",
    "security_reviewer": "ai-team-reviewer",
    "documentation": "ai-team-documentation",
    "final_gate": "ai-team-release",
}

# Backward-compatible stage aliases for callers created before the canonical role names.
ROLE_ALIASES = {"product": "orchestrator", "refactor": "developer", "qa": "tester", "release": "final_gate"}

ROLE_CAPABILITIES = {
    "orchestrator": "reasoning", "architect": "reasoning", "developer": "coding",
    "debugger": "coding", "reviewer": "review", "tester": "coding",
    "security_reviewer": "review", "documentation": "coding", "final_gate": "review",
}

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "vendor",
    "dist", "build", ".next", "coverage", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".cache", "target", "omniroute-data",
    ".ai-team/runtime", ".ai-team/logs",
}

BINARY_SUFFIXES = {
    ".7z", ".avi", ".bin", ".bmp", ".class", ".dll", ".doc", ".docx",
    ".exe", ".gif", ".gz", ".ico", ".jar", ".jpeg", ".jpg", ".lockb",
    ".mov", ".mp3", ".mp4", ".o", ".obj", ".pdf", ".png", ".pyc",
    ".so", ".tar", ".webm", ".woff", ".woff2", ".xlsx", ".zip",
}

SENSITIVE_FILENAMES = {
    ".env", ".env.local", ".env.development", ".env.production", ".env.test",
    "credentials.json", "secrets.json", "id_rsa", "id_ed25519",
}

SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".crt", ".cer"}
