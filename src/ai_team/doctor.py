from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .models import find_codex_executable
from .provider_registry import discover_providers
from .skills import SkillLoader, validate_role_contracts


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    required: bool = True
    timestamp: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"PASS", "AVAILABLE", "CONFIGURED"}


def _check(name: str, status: str, detail: str, required: bool = True) -> Check:
    return Check(name, status, detail, required, datetime.now(timezone.utc).isoformat())


def _command(name: str, *args: str, required: bool = True) -> Check:
    executable = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not executable: return _check(name, "FAIL" if required else "UNAVAILABLE", "not found", required)
    result = subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=30)
    detail = (result.stdout or result.stderr).strip().splitlines()
    return _check(name, "PASS" if result.returncode == 0 else "FAIL", detail[0] if detail else executable, required)


def _ollama_models() -> tuple[Check, set[str]]:
    executable = shutil.which("ollama")
    if not executable: return _check("ollama-runtime", "FAIL", "not found"), set()
    result = subprocess.run([executable, "list"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=30)
    models = {line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()}
    return _check("ollama-runtime", "PASS" if result.returncode == 0 else "FAIL", f"{len(models)} models detected"), models


def _request_json(url: str, settings: Settings, payload: dict | None = None, timeout: float = 10) -> dict:
    data = json.dumps(payload).encode() if payload else None
    headers = {"Authorization": f"Bearer {settings.omniroute_api_key}"}
    if data: headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200: raise RuntimeError(f"HTTP {response.status}")
        value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict): raise RuntimeError("malformed JSON response")
        return value


def _route_probe(settings: Settings, role: str, expected: str) -> Check:
    model = settings.model_for(role)
    nonce = datetime.now(timezone.utc).isoformat()
    payload = {"model": model, "messages": [{"role": "system", "content": settings.routing_marker_for(role)},
              {"role": "user", "content": f"Reply exactly ROUTE_OK. Probe timestamp: {nonce}"}], "max_tokens": 1200, "temperature": 0,
              }
    if role == "reviewer":
        payload["reasoning_effort"] = "low"
    try:
        result = _request_json(settings.omniroute_base_url + "/chat/completions", settings, payload, settings.provider_timeout_seconds)
        returned = str(result.get("model", ""))
        choices = result.get("choices") or []
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        ok = expected.casefold() in returned.casefold() and bool(str(content).strip())
        return _check(f"route:{role}", "PASS" if ok else "FAIL", f"requested={model}; returned={returned or 'missing'}; nonempty={bool(str(content).strip())}")
    except (OSError, urllib.error.URLError, ValueError, RuntimeError) as exc:
        return _check(f"route:{role}", "FAIL", f"probe failed: {type(exc).__name__}")


def run_doctor(settings: Settings, write_root: Path | None = None, *, live_routes: bool = True) -> list[Check]:
    checks = [_command("git", "--version")]
    checks.append(_check("python>=3.11", "PASS" if sys.version_info >= (3, 11) else "FAIL", sys.version.split()[0]))
    target = (write_root or Path.cwd()).resolve()
    try:
        skills = SkillLoader(settings.skills_root).validate_all()
        framework_contracts = Path(__file__).resolve().parents[2] / ".ai-team" / "roles" / "contracts.yaml"
        validate_role_contracts(framework_contracts)
        checks.append(_check("role-contracts", "PASS", f"{len(skills)} valid role mappings and project contracts"))
    except Exception as exc: checks.append(_check("role-contracts", "FAIL", str(exc)))
    try:
        with tempfile.NamedTemporaryFile(prefix="ai-team-doctor-", dir=target, delete=True): pass
        checks.append(_check("write-permission", "PASS", str(target)))
    except OSError as exc: checks.append(_check("write-permission", "FAIL", type(exc).__name__))
    ollama, models = _ollama_models(); checks.append(ollama)
    for model in ("qwen3-coder:30b", "gpt-oss:20b"):
        checks.append(_check(f"model:{model}", "AVAILABLE" if model in models else "FAIL", "available" if model in models else "missing"))
    try:
        catalog = _request_json(settings.omniroute_base_url + "/models", settings)
        entries = catalog.get("data")
        if not isinstance(entries, list): raise RuntimeError("models payload is malformed")
        checks.append(_check("omniroute-api", "PASS", f"HTTP 200; {len(entries)} advertised models"))
        providers = discover_providers(entries, free_tier_enabled=settings.free_tier_enabled)
        local = next((item for item in providers if item.classification.value == "LOCAL"), None)
        checks.append(_check("provider-discovery", "AVAILABLE", f"{len(providers)} classified; local_eligible={bool(local and local.eligible)}", False))
    except Exception as exc:
        checks.append(_check("omniroute-api", "FAIL", f"API unavailable: {type(exc).__name__}"))
        checks.append(_check("provider-discovery", "UNAVAILABLE", "local core discovery unavailable", False))
    if live_routes:
        checks += [_route_probe(settings, "developer", "qwen3-coder:30b"), _route_probe(settings, "reviewer", "gpt-oss:20b")]
    executable = find_codex_executable()
    if settings.codex_enabled:
        checks.append(_check("codex-configuration", "CONFIGURED" if executable else "FAIL", "executable found" if executable else "enabled but unavailable"))
    else:
        checks.append(_check("codex-configuration", "NOT_CONFIGURED", "disabled by policy", False))
    return checks


def format_doctor(checks: list[Check], as_json: bool = False) -> str:
    if as_json: return json.dumps([asdict(check) | {"ok": check.ok} for check in checks], indent=2)
    lines = [f"{item.status}  {item.name}: {item.detail}" for item in checks]
    lines.append(f"OVERALL: {'PASS' if all(item.ok for item in checks if item.required) else 'FAIL'}")
    return "\n".join(lines)
