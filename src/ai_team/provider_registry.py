from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ProviderClass(StrEnum):
    LOCAL = "LOCAL"
    FREE = "FREE"
    FREE_TIER = "FREE-TIER"
    PAID = "PAID"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProviderRecord:
    provider: str
    classification: ProviderClass
    eligible: bool
    evidence: str


def classify_provider(provider: str, evidence: dict[str, Any] | None = None, *, free_tier_enabled: bool = False) -> ProviderRecord:
    name = provider.lower().strip()
    evidence = evidence or {}
    if name in {"ollama", "ollama-local", "lmstudio", "local"} or evidence.get("local") is True:
        category = ProviderClass.LOCAL
    elif evidence.get("free") is True and evidence.get("billing_required") is False:
        category = ProviderClass.FREE
    elif evidence.get("free_tier") is True:
        category = ProviderClass.FREE_TIER
    elif evidence.get("paid") is True or name in {"openai", "anthropic", "codex"}:
        category = ProviderClass.PAID
    else:
        category = ProviderClass.UNKNOWN
    eligible = category in {ProviderClass.LOCAL, ProviderClass.FREE} or (
        category is ProviderClass.FREE_TIER and free_tier_enabled and evidence.get("no_billing") is True
    )
    return ProviderRecord(provider, category, eligible, "current discovery metadata" if evidence else "name-only classification")


def discover_providers(models: list[dict[str, Any]], *, free_tier_enabled: bool = False) -> list[ProviderRecord]:
    evidence_by_provider: dict[str, dict[str, Any]] = {}
    for model in models:
        provider = str(model.get("owned_by") or str(model.get("id", "")).split("/", 1)[0] or "unknown")
        current = evidence_by_provider.setdefault(provider, {})
        if "local" in provider.casefold() or str(model.get("id", "")).casefold().startswith("ollama/"):
            current["local"] = True
        pricing = model.get("pricing")
        if isinstance(pricing, dict):
            values = [value for value in pricing.values() if isinstance(value, (int, float))]
            if values and all(value == 0 for value in values):
                current.update(free=True, billing_required=False)
            elif any(value > 0 for value in values):
                current["paid"] = True
    return [classify_provider(name, evidence, free_tier_enabled=free_tier_enabled)
            for name, evidence in sorted(evidence_by_provider.items())]
