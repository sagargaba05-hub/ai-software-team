from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .constants import ROLE_ALIASES, ROLE_CAPABILITIES, ROLE_SKILLS


@dataclass(frozen=True)
class RoleSkill:
    role: str
    name: str
    description: str
    instructions: str
    path: Path
    capability: str
    project_constraints: str = ""


class SkillError(ValueError):
    pass


REQUIRED_CONTRACT_FIELDS = {"responsibility", "entry", "output", "preferred", "fallback", "escalation", "complete"}


def validate_role_contracts(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        raise SkillError(f"Missing role contracts: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SkillError(f"Unreadable role contracts: {path}: {exc}") from exc
    roles = payload.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLE_SKILLS):
        raise SkillError("Role contracts must contain exactly the authoritative role set")
    for role, contract in roles.items():
        if not isinstance(contract, dict) or not REQUIRED_CONTRACT_FIELDS.issubset(contract):
            raise SkillError(f"Incomplete role contract: {role}")
        if any(not isinstance(contract[field], str) or not contract[field].strip() for field in REQUIRED_CONTRACT_FIELDS):
            raise SkillError(f"Empty role contract field: {role}")
    return roles


class SkillLoader:
    def __init__(self, root: Path):
        self.root = root

    def load(self, role: str, repository: Path | None = None) -> RoleSkill:
        role = ROLE_ALIASES.get(role, role)
        if role not in ROLE_SKILLS:
            raise SkillError(f"Unknown role: {role}")
        expected = ROLE_SKILLS[role]
        path = self.root / expected / "SKILL.md"
        if not path.is_file():
            raise SkillError(f"Missing skill: {path}")
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---\n"):
            raise SkillError(f"Missing YAML front matter: {path}")
        try:
            _, front, body = raw.split("---", 2)
            metadata = yaml.safe_load(front) or {}
        except Exception as exc:
            raise SkillError(f"Invalid front matter in {path}: {exc}") from exc
        name = metadata.get("name")
        description = metadata.get("description")
        if name != expected:
            raise SkillError(f"Expected skill name {expected!r}, got {name!r}")
        if not isinstance(description, str) or not description.strip():
            raise SkillError(f"Missing skill description: {path}")
        if not body.strip():
            raise SkillError(f"Missing skill instructions: {path}")
        project_constraints = ""
        if repository is not None:
            rules = repository / "AGENTS.md"
            if rules.is_file():
                project_constraints = rules.read_text(encoding="utf-8", errors="replace").strip()
        return RoleSkill(role, name, description.strip(), body.strip(), path, ROLE_CAPABILITIES[role], project_constraints)

    def validate_all(self) -> list[RoleSkill]:
        return [self.load(role) for role in ROLE_SKILLS]
