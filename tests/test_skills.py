"""Tests for the GTD skills file loader (src.common.skills)."""

from pathlib import Path

import pytest

from src.common.skills import DEFAULT_SKILLS_PATH, SkillsFileError, load_skills


class TestLoadSkills:
    """Tests for load_skills()."""

    def test_loads_default_skills_file(self) -> None:
        """The default skills file (skills/gtd.md) loads successfully."""
        content = load_skills()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_default_path_points_to_repo_file(self) -> None:
        """DEFAULT_SKILLS_PATH resolves to the repo's skills/gtd.md."""
        assert DEFAULT_SKILLS_PATH.name == "gtd.md"
        assert DEFAULT_SKILLS_PATH.parent.name == "skills"
        assert DEFAULT_SKILLS_PATH.exists()

    def test_content_has_expected_sections(self) -> None:
        """The skills file contains key GTD sections."""
        content = load_skills()
        assert "Five Phases" in content or "five phases" in content.lower()
        assert "Two-Minute Rule" in content
        assert "Context Tags" in content or "context tags" in content.lower()
        assert "Eisenhower Matrix" in content or "eisenhower" in content.lower()
        assert "Weekly Review" in content
        assert "Horizons of Focus" in content

    def test_loads_from_explicit_path(self, tmp_path: Path) -> None:
        """load_skills() accepts an explicit path."""
        skills_file = tmp_path / "custom_gtd.md"
        skills_file.write_text("# Custom GTD\nSome content.", encoding="utf-8")
        content = load_skills(skills_file)
        assert content == "# Custom GTD\nSome content."

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        """SkillsFileError is raised when the file does not exist."""
        missing = tmp_path / "nonexistent.md"
        with pytest.raises(SkillsFileError, match="not found"):
            load_skills(missing)

    def test_raises_on_directory(self, tmp_path: Path) -> None:
        """SkillsFileError is raised when the path is a directory."""
        with pytest.raises(SkillsFileError, match="not a file"):
            load_skills(tmp_path)

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        """SkillsFileError is raised when the file is empty."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises(SkillsFileError, match="empty"):
            load_skills(empty_file)

    def test_raises_on_whitespace_only_file(self, tmp_path: Path) -> None:
        """SkillsFileError is raised for a file with only whitespace."""
        ws_file = tmp_path / "whitespace.md"
        ws_file.write_text("   \n\n  \t  \n", encoding="utf-8")
        with pytest.raises(SkillsFileError, match="empty"):
            load_skills(ws_file)

    def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Paths with ~ are expanded correctly."""
        skills_file = tmp_path / "gtd.md"
        skills_file.write_text("# GTD content", encoding="utf-8")

        def _fake_expanduser(self: Path) -> Path:
            return tmp_path / self.name if "~" in str(self) else self

        monkeypatch.setattr(Path, "expanduser", _fake_expanduser)
        content = load_skills(Path("~/gtd.md"))
        assert "GTD content" in content

    def test_content_is_well_formed_markdown(self) -> None:
        """The default skills file starts with a Markdown heading."""
        content = load_skills()
        assert content.lstrip().startswith("#")
