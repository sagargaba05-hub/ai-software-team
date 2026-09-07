from pathlib import Path

from ai_team.documents import DOCS, bootstrap_project
from ai_team.repository import inspect_repository


def test_document_bootstrap_is_non_destructive(tmp_path: Path):
    (tmp_path / "README.md").write_text("existing", encoding="utf-8")
    created = bootstrap_project(tmp_path)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "existing"
    assert (tmp_path / "AGENTS.md").exists()
    assert all((tmp_path / "docs" / name).exists() for name in DOCS)
    assert (tmp_path / ".ai-team" / "test-results").is_dir()
    assert created


def test_repository_excludes_generated_and_binary_content(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "index.js").write_text("ignored", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"png")
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=", encoding="utf-8")
    files = inspect_repository(tmp_path).files
    assert Path("src/app.py") in files
    assert not any("node_modules" in path.parts for path in files)
    assert Path("image.png") not in files
    assert Path(".env") not in files
    assert Path(".env.example") in files
