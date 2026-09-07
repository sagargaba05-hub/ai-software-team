from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_KEYS = re.compile(r"(?i)(api[_-]?key|authorization|password|secret|token|credential|private[_-]?key)")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if _SECRET_KEYS.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _BEARER.sub("Bearer [REDACTED]", value)
    return value


class AuditLog:
    def __init__(self, repository: Path):
        self.directory = repository / ".ai-team" / "logs"

    def append(self, stream: str, event: dict[str, Any]) -> Path:
        if stream not in {"usage", "escalations"}:
            raise ValueError(f"Unsupported audit stream: {stream}")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{stream}.jsonl"
        record = {"timestamp": utc_now(), **redact(event)}
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return path
