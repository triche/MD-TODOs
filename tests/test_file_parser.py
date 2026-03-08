"""Unit tests for the file parser (regex + AI combined)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.ai.provider import AIProviderError
from src.extractor.file_parser import parse_file, parse_file_async


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    """Create a temporary notes directory."""
    d = tmp_path / "notes"
    d.mkdir()
    return d


@pytest.fixture
def sample_md(notes_dir: Path) -> Path:
    """Create a sample Markdown file with mixed content."""
    content = """\
# Meeting Notes

- [ ] Buy groceries
- [x] Send email

Some random prose here.

I need to schedule a dentist appointment before the end of the month.

TODO: Fix the login bug
"""
    p = notes_dir / "sample.md"
    p.write_text(content, encoding="utf-8")
    return p


class TestParseFileRegexOnly:
    """Test the parser with AI disabled (regex only)."""

    def test_regex_detection(self, sample_md: Path, notes_dir: Path) -> None:
        items = parse_file(sample_md, notes_dir, implicit_detection=False)
        # Should find: 2 checkboxes + 1 keyword = 3
        assert len(items) == 3
        texts = [i.text for i in items]
        assert "Buy groceries" in texts
        assert "Send email" in texts
        assert "Fix the login bug" in texts

    def test_sorted_by_line(self, sample_md: Path, notes_dir: Path) -> None:
        items = parse_file(sample_md, notes_dir, implicit_detection=False)
        lines = [i.source_line for i in items]
        assert lines == sorted(lines)

    def test_source_file_relative(self, sample_md: Path, notes_dir: Path) -> None:
        items = parse_file(sample_md, notes_dir, implicit_detection=False)
        assert all(i.source_file == "sample.md" for i in items)

    def test_file_not_found(self, notes_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_file(notes_dir / "nonexistent.md", notes_dir)

    def test_empty_file(self, notes_dir: Path) -> None:
        empty = notes_dir / "empty.md"
        empty.write_text("", encoding="utf-8")
        items = parse_file(empty, notes_dir, implicit_detection=False)
        assert items == []

    def test_no_todos(self, notes_dir: Path) -> None:
        plain = notes_dir / "plain.md"
        plain.write_text("# Just a heading\n\nSome text.\n", encoding="utf-8")
        items = parse_file(plain, notes_dir, implicit_detection=False)
        assert items == []


class TestParseFileWithAI:
    """Test the parser with AI enabled (mocked provider)."""

    @pytest.fixture
    def mock_provider(self) -> AsyncMock:
        provider = AsyncMock()
        provider.complete = AsyncMock(return_value="not_action_item")
        return provider

    @pytest.mark.asyncio
    async def test_ai_adds_implicit_todos(
        self, sample_md: Path, notes_dir: Path, mock_provider: AsyncMock
    ) -> None:
        # Make AI detect the dentist paragraph as an action item
        async def _classify(system_prompt: str, user_prompt: str, options: object = None) -> str:
            return "action_item" if "dentist" in user_prompt else "not_action_item"

        mock_provider.complete = AsyncMock(side_effect=_classify)

        items = await parse_file_async(
            sample_md, notes_dir, provider=mock_provider, implicit_detection=True
        )

        # 3 regex + 1 AI = 4
        assert len(items) == 4
        ai_items = [i for i in items if i.detection_method == "ai_implicit"]
        assert len(ai_items) == 1
        assert "dentist" in ai_items[0].text

    @pytest.mark.asyncio
    async def test_ai_failure_falls_back_to_regex(
        self, sample_md: Path, notes_dir: Path, mock_provider: AsyncMock
    ) -> None:
        """When AI fails entirely, regex results are still returned."""
        mock_provider.complete = AsyncMock(side_effect=AIProviderError("down"))

        items = await parse_file_async(
            sample_md, notes_dir, provider=mock_provider, implicit_detection=True
        )

        # Only regex items
        assert len(items) == 3
        assert all(i.detection_method in ("checkbox", "keyword") for i in items)

    @pytest.mark.asyncio
    async def test_no_provider_skips_ai(self, sample_md: Path, notes_dir: Path) -> None:
        """When no provider is given, AI detection is skipped."""
        items = await parse_file_async(sample_md, notes_dir, provider=None, implicit_detection=True)
        assert len(items) == 3


class TestParseFileSubdirectory:
    """Test relative path computation for files in subdirectories."""

    def test_nested_file(self, notes_dir: Path) -> None:
        sub = notes_dir / "2024" / "06"
        sub.mkdir(parents=True)
        f = sub / "meeting.md"
        f.write_text("- [ ] Review slides\n", encoding="utf-8")

        items = parse_file(f, notes_dir, implicit_detection=False)
        assert len(items) == 1
        assert items[0].source_file == "2024/06/meeting.md"
