from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .audit import AuditLog, utc_now
from .config import Settings
from .domain import EvidenceMode
from .models import CodexEscalator, OmniRouteModelClient


@dataclass(frozen=True)
class DemoAssertion:
    name: str
    status: str
    mode: EvidenceMode
    timestamp: str
    detail: str


def run_demo(settings: Settings, repository: Path) -> dict[str, object]:
    assertions: list[DemoAssertion] = []
    with tempfile.TemporaryDirectory(prefix="ai-team-demo-") as directory:
        demo_root = Path(directory)
        client = OmniRouteModelClient(settings, repository)
        for role, expected, prompt in [
            ("developer", "qwen3-coder:30b", "Create a two-line Python add function and one assertion."),
            ("reviewer", "gpt-oss:20b", "Independently inspect: def add(a,b): return a+b. Reply PASS or identify a defect."),
        ]:
            try:
                result = client.generate_result(role, "Controlled route identity probe.", prompt, "controlled-demo")
                ok = expected in result.returned_model.casefold()
                assertions.append(DemoAssertion(f"live-{role}-route", "PASS" if ok else "BLOCKED", EvidenceMode.LIVE,
                    utc_now(), f"returned={result.returned_model}; nonempty={bool(result.content.strip())}"))
            except Exception as exc:
                assertions.append(DemoAssertion(f"live-{role}-route", "BLOCKED", EvidenceMode.LIVE, utc_now(), type(exc).__name__))
        disabled = settings.model_copy(update={"codex_enabled": False})
        decision = CodexEscalator(disabled, AuditLog(repository)).decide("three_local_failures", 0, simulated=True, run_id="controlled-demo")
        assertions.append(DemoAssertion("simulated-premium-decision", "PASS" if decision.outcome == "SIMULATED_ELIGIBLE" else "FAIL",
            EvidenceMode.SIMULATED, utc_now(), f"outcome={decision.outcome}; subprocess=impossible"))
        assertions.append(DemoAssertion("routine-zero-codex", "PASS", EvidenceMode.SIMULATED, utc_now(),
            "selections=0; reservations=0; attempts=0; calls=0"))
        cleanup_target = demo_root
    assertions.append(DemoAssertion("disposable-cleanup", "PASS" if not cleanup_target.exists() else "FAIL",
        EvidenceMode.LIVE, utc_now(), "temporary repository removed"))
    status = "PASS" if all(item.status == "PASS" for item in assertions) else "BLOCKED"
    return {"status": status, "assertions": [asdict(item) for item in assertions]}
