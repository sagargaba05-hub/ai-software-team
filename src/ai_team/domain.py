from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Capability(StrEnum):
    CODING = "coding"
    REASONING = "reasoning"
    REVIEW = "review"


class WorkKind(StrEnum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    REVIEW_ONLY = "review-only"


class TerminalState(StrEnum):
    RELEASE_APPROVED = "RELEASE_APPROVED"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class EvidenceMode(StrEnum):
    LIVE = "LIVE"
    SIMULATED = "SIMULATED"


class Severity(StrEnum):
    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    SUGGESTION = "SUGGESTION"


@dataclass(frozen=True)
class WorkProfile:
    kind: WorkKind
    security_required: bool
    security_reason: str


@dataclass(frozen=True)
class RolePlan:
    roles: tuple[str, ...]
    profile: WorkProfile


@dataclass(frozen=True)
class RoleRequest:
    run_id: str
    role: str
    capability: Capability
    objective: str
    context: str = ""


@dataclass(frozen=True)
class RouteDecision:
    capability: Capability
    model: str
    route_type: str
    reason: str


@dataclass(frozen=True)
class Finding:
    severity: Severity
    summary: str
    owner: str
    evidence: tuple[str, ...] = ()
    resolved: bool = False


@dataclass(frozen=True)
class Evidence:
    reference: str
    mode: EvidenceMode
    timestamp: str
    result: str


@dataclass(frozen=True)
class StageResult:
    role: str
    status: str
    summary: str
    findings: tuple[Finding, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
