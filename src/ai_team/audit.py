from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET_KEYS = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret|token|credential|private[_-]?key)"
)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_AUTHORIZATION_ASSIGNMENT = re.compile(
    r"(?i)\bauthorization(\s*[:=]\s*)"
    r"(\"[^\"]*\"|'[^']*'|(?:basic|bearer)\s+[^\s,;]+|[^\s,;]+)"
)
_EMBEDDED_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token|credential|private[_-]?key)"
    r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_ACTIVE_RUN_ID: ContextVar[str | None] = ContextVar(
    "ai_team_active_run_id", default=None
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if _SECRET_KEYS.search(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = _AUTHORIZATION_ASSIGNMENT.sub(
            lambda match: f"authorization{match.group(1)}[REDACTED]", value
        )
        value = _BEARER.sub("Bearer [REDACTED]", value)
        return _EMBEDDED_SECRET.sub(
            lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value
        )
    return value


@contextmanager
def audit_run(run_id: str):
    token = _ACTIVE_RUN_ID.set(run_id)
    try:
        yield
    finally:
        _ACTIVE_RUN_ID.reset(token)


class AuditLog:
    def __init__(self, repository: Path):
        self.directory = repository / ".ai-team" / "logs"

    def append(self, stream: str, event: dict[str, Any]) -> Path:
        if stream not in {"usage", "escalations"}:
            raise ValueError(f"Unsupported audit stream: {stream}")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{stream}.jsonl"
        event = dict(event)
        active_run_id = _ACTIVE_RUN_ID.get()
        if active_run_id and event.get("run_id") in {None, "", "unbound"}:
            event["run_id"] = active_run_id
        record = {"timestamp": utc_now(), **redact(event)}
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return path
