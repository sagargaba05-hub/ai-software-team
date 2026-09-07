from pathlib import Path

import pytest

from ai_team.constants import ROLE_SKILLS


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    for name in set(ROLE_SKILLS.values()):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Run the {name} role when its delivery stage is active.\n---\n\n# Role\n\nFollow the stage contract.\n",
            encoding="utf-8",
        )
    return root
