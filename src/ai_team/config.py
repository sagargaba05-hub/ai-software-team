from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from .constants import ROLE_ALIASES, ROLE_CAPABILITIES
from .domain import Capability, RouteDecision


class Settings(BaseModel):
    omniroute_base_url: str = "http://127.0.0.1:20128/v1"
    omniroute_api_key: str = "local-omniroute"
    model_coding_route: str = "ollama/qwen3-coder:30b"
    model_reasoning_route: str = "ollama/gpt-oss:20b"
    model_review_route: str = "ollama/gpt-oss:20b"
    max_local_rework_loops: int = Field(default=3, ge=1, le=3)
    max_context_files: int = Field(default=30, ge=1, le=500)
    max_context_chars: int = Field(default=80_000, ge=1_000, le=2_000_000)
    provider_attempts: int = Field(default=2, ge=1, le=5)
    provider_timeout_seconds: float = Field(default=300, gt=0, le=900)
    mcp_timeout_seconds: int = Field(default=14_400, ge=1, le=86_400)
    max_codex_calls_per_run: int = Field(default=3, ge=0, le=20)
    codex_timeout_seconds: int = Field(default=1800, ge=1, le=7200)
    codex_max_output_chars: int = Field(default=40_000, ge=1000, le=200_000)
    demo_timeout_seconds: int = Field(default=600, ge=10, le=1800)
    demo_max_context_chars: int = Field(default=8_000, ge=500, le=50_000)
    free_tier_enabled: bool = False
    codex_enabled: bool = False
    codex_final_review: bool = False
    skills_root: Path = Path.home() / ".agents" / "skills"

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(env_file or Path.cwd() / ".env", override=False)
        return cls(
            omniroute_base_url=os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1"),
            omniroute_api_key=os.getenv("OMNIROUTE_API_KEY", "local-omniroute"),
            model_coding_route=os.getenv("MODEL_CODING_ROUTE", "ollama/qwen3-coder:30b"),
            model_reasoning_route=os.getenv("MODEL_REASONING_ROUTE", "ollama/gpt-oss:20b"),
            model_review_route=os.getenv("MODEL_REVIEW_ROUTE", "ollama/gpt-oss:20b"),
            max_local_rework_loops=int(os.getenv("MAX_LOCAL_REWORK_LOOPS", "3")),
            max_context_files=int(os.getenv("MAX_CONTEXT_FILES", "30")),
            max_context_chars=int(os.getenv("MAX_CONTEXT_CHARS", "80000")),
            provider_attempts=int(os.getenv("PROVIDER_ATTEMPTS", "2")),
            provider_timeout_seconds=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "300")),
            mcp_timeout_seconds=int(os.getenv("MCP_TIMEOUT_SECONDS", "14400")),
            max_codex_calls_per_run=int(os.getenv("MAX_CODEX_CALLS_PER_RUN", "3")),
            codex_timeout_seconds=int(os.getenv("CODEX_TIMEOUT_SECONDS", "1800")),
            codex_max_output_chars=int(os.getenv("CODEX_MAX_OUTPUT_CHARS", "40000")),
            demo_timeout_seconds=int(os.getenv("DEMO_TIMEOUT_SECONDS", "600")),
            demo_max_context_chars=int(os.getenv("DEMO_MAX_CONTEXT_CHARS", "8000")),
            free_tier_enabled=os.getenv("FREE_TIER_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
            codex_enabled=os.getenv("CODEX_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
            codex_final_review=os.getenv("CODEX_FINAL_REVIEW", "false").lower() in {"1", "true", "yes", "on"},
            skills_root=Path(os.getenv("AI_TEAM_SKILLS_ROOT", str(Path.home() / ".agents" / "skills"))),
        )

    @field_validator("omniroute_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("OmniRoute base URL must use http or https")
        return value.rstrip("/")

    def capability_for(self, role: str) -> Capability:
        role = ROLE_ALIASES.get(role, role)
        try:
            return Capability(ROLE_CAPABILITIES[role])
        except KeyError as exc:
            raise ValueError(f"Unknown role: {role}") from exc

    def route_for(self, capability: Capability) -> RouteDecision:
        if capability is Capability.CODING:
            return RouteDecision(capability, self.model_coding_route, "LOCAL", "coding capability default")
        if capability is Capability.REVIEW:
            return RouteDecision(capability, self.model_review_route, "LOCAL", "independent review default")
        return RouteDecision(capability, self.model_reasoning_route, "LOCAL", "reasoning capability default")

    def model_for(self, role: str) -> str:
        return self.route_for(self.capability_for(role)).model

    def routing_marker_for(self, role: str) -> str:
        if self.capability_for(role) is Capability.CODING:
            return "AI_TEAM_ROUTE_CODING"
        return "AI_TEAM_ROUTE_REASONING"
