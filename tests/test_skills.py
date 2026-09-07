from ai_team.constants import ROLE_SKILLS
import pytest

from ai_team.skills import SkillError, SkillLoader, validate_role_contracts


def test_discovers_all_global_role_shapes(skills_root):
    loaded = SkillLoader(skills_root).validate_all()
    assert {skill.name for skill in loaded} == set(ROLE_SKILLS.values())
    assert all(skill.instructions for skill in loaded)


def test_rejects_wrong_skill_name(skills_root):
    path = skills_root / "ai-team-qa" / "SKILL.md"
    path.write_text("---\nname: wrong\ndescription: wrong\n---\nbody", encoding="utf-8")
    try:
        SkillLoader(skills_root).load("qa")
    except ValueError as exc:
        assert "Expected skill name" in str(exc)
    else:
        raise AssertionError("invalid skill was accepted")


def test_role_contract_validation_requires_exact_complete_set(tmp_path):
    path = tmp_path / "contracts.yaml"
    path.write_text("roles: {}\n", encoding="utf-8")
    with pytest.raises(SkillError, match="exactly"):
        validate_role_contracts(path)
