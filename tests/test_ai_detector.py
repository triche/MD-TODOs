"""Unit tests for the AI-based implicit TODO detector."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.common.todo_models import TodoItem
from src.extractor.ai_detector import (
    _extract_action_text,
    _paragraph_overlaps_regex,
    _split_paragraphs,
    detect_implicit_todos,
)

# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestSplitParagraphs:
    def test_single_paragraph(self) -> None:
        text = "Hello world\nSecond line"
        paras = _split_paragraphs(text)
        assert len(paras) == 1
        assert paras[0] == ("Hello world\nSecond line", 1)

    def test_two_paragraphs(self) -> None:
        text = "First paragraph\n\nSecond paragraph"
        paras = _split_paragraphs(text)
        assert len(paras) == 2
        assert paras[0] == ("First paragraph", 1)
        assert paras[1] == ("Second paragraph", 3)

    def test_multiple_blank_lines(self) -> None:
        text = "Para one\n\n\n\nPara two"
        paras = _split_paragraphs(text)
        assert len(paras) == 2
        assert paras[0][0] == "Para one"
        assert paras[1][0] == "Para two"

    def test_empty_text(self) -> None:
        assert _split_paragraphs("") == []

    def test_only_blank_lines(self) -> None:
        assert _split_paragraphs("\n\n\n") == []

    def test_multiline_paragraph(self) -> None:
        text = "Line 1\nLine 2\nLine 3\n\nLine 5"
        paras = _split_paragraphs(text)
        assert len(paras) == 2
        assert paras[0] == ("Line 1\nLine 2\nLine 3", 1)
        assert paras[1] == ("Line 5", 5)

    def test_trailing_newline(self) -> None:
        text = "Paragraph\n"
        paras = _split_paragraphs(text)
        assert len(paras) == 1
        assert paras[0][0] == "Paragraph"


class TestParagraphOverlapsRegex:
    def test_overlap(self) -> None:
        covered = {3, 5}
        assert _paragraph_overlaps_regex(3, "one line", covered) is True

    def test_multiline_overlap(self) -> None:
        covered = {4}
        # Para starts at line 3, has 3 lines (3, 4, 5)
        assert _paragraph_overlaps_regex(3, "line1\nline2\nline3", covered) is True

    def test_no_overlap(self) -> None:
        covered = {10, 20}
        assert _paragraph_overlaps_regex(1, "one\ntwo", covered) is False


class TestExtractActionText:
    def test_short_text(self) -> None:
        assert _extract_action_text("Do something") == "Do something"

    def test_long_text_with_sentence(self) -> None:
        text = "This is a long sentence that goes on. And another follows with more text."
        result = _extract_action_text(text * 3)
        assert result.endswith(".")
        assert len(result) <= 200  # reasonable

    def test_whitespace_collapse(self) -> None:
        result = _extract_action_text("  Do  \n  something  ")
        assert result == "Do something"


# ---------------------------------------------------------------------------
# AI detection (mocked provider)
# ---------------------------------------------------------------------------


class TestDetectImplicitTodos:
    @pytest.fixture
    def mock_provider(self) -> AsyncMock:
        provider = AsyncMock()
        provider.complete = AsyncMock(return_value="not_action_item")
        return provider

    @pytest.mark.asyncio
    async def test_no_candidates(self, mock_provider: AsyncMock) -> None:
        """When all paragraphs overlap regex items, no AI calls are made."""
        text = "- [ ] Buy milk\n\nShort"
        regex_items = [
            TodoItem(
                text="Buy milk",
                source_file="test.md",
                source_line=1,
                detection_method="checkbox",
            )
        ]
        result = await detect_implicit_todos(text, "test.md", mock_provider, regex_items)
        assert result == []
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_item_detected(self, mock_provider: AsyncMock) -> None:
        """When AI classifies a paragraph as an action item, a TodoItem is returned."""
        text = (
            "Some normal heading\n\n"
            "I need to schedule a dentist appointment soon.\n\n"
            "- [ ] Buy milk"
        )
        regex_items = [
            TodoItem(
                text="Buy milk",
                source_file="test.md",
                source_line=5,
                detection_method="checkbox",
            )
        ]
        mock_provider.complete = AsyncMock(return_value="action_item")

        result = await detect_implicit_todos(text, "test.md", mock_provider, regex_items)
        # Only paragraphs not overlapping regex should be sent
        # "Some normal heading" is <15 chars? No, it's 19 chars. So both paragraphs get sent.
        # "Some normal heading" → action_item, "I need to schedule..." → action_item
        assert len(result) >= 1
        assert all(item.detection_method == "ai_implicit" for item in result)

    @pytest.mark.asyncio
    async def test_not_action_item(self, mock_provider: AsyncMock) -> None:
        """Paragraphs classified as not_action_item are excluded."""
        text = "This is just some random prose that has no action items at all."
        mock_provider.complete = AsyncMock(return_value="not_action_item")

        result = await detect_implicit_todos(text, "test.md", mock_provider, [])
        assert result == []
        mock_provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_classification(self, mock_provider: AsyncMock) -> None:
        """Test with multiple paragraphs, some action items, some not."""
        text = (
            "This is a meeting note about project status.\n\n"
            "We need to finish the report by Friday.\n\n"
            "The weather was nice today."
        )
        # First call: not action, second: action, third: not action
        mock_provider.complete = AsyncMock(
            side_effect=["not_action_item", "action_item", "not_action_item"]
        )

        result = await detect_implicit_todos(text, "test.md", mock_provider, [])
        assert len(result) == 1
        assert "finish the report" in result[0].text
        assert result[0].detection_method == "ai_implicit"
        assert result[0].source_file == "test.md"

    @pytest.mark.asyncio
    async def test_completed_action_item(self, mock_provider: AsyncMock) -> None:
        """Paragraphs classified as completed_action_item get status='done'."""
        text = (
            "~~I need to schedule a dentist appointment.~~\n\n"
            "We need to finish the report by Friday."
        )
        mock_provider.complete = AsyncMock(side_effect=["completed_action_item", "action_item"])

        result = await detect_implicit_todos(text, "test.md", mock_provider, [])
        assert len(result) == 2
        completed = [i for i in result if i.status == "done"]
        assert len(completed) == 1
        assert "dentist" in completed[0].text
        assert completed[0].detection_method == "ai_implicit"
        open_items = [i for i in result if i.status == "open"]
        assert len(open_items) == 1
        assert "finish the report" in open_items[0].text

    @pytest.mark.asyncio
    async def test_ai_error_gracefully_skips(self, mock_provider: AsyncMock) -> None:
        """When the AI provider raises, the paragraph is skipped."""
        from src.ai.provider import AIProviderError

        text = "I need to call the doctor about the test results."
        mock_provider.complete = AsyncMock(side_effect=AIProviderError("timeout"))

        result = await detect_implicit_todos(text, "test.md", mock_provider, [])
        assert result == []

    @pytest.mark.asyncio
    async def test_invalid_label_logged_and_skipped(
        self, mock_provider: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When the AI provider returns an unrecognised label, the paragraph is skipped and a warning is logged."""
        import logging

        text = "I need to call the doctor about the test results."
        mock_provider.complete = AsyncMock(return_value="maybe")

        with caplog.at_level(logging.WARNING, logger="src.extractor.ai_detector"):
            result = await detect_implicit_todos(text, "test.md", mock_provider, [])

        assert result == []
        assert any("maybe" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_short_paragraphs_skipped(self, mock_provider: AsyncMock) -> None:
        """Paragraphs shorter than the minimum length are not sent to AI."""
        text = "Short\n\nAlso tiny"
        result = await detect_implicit_todos(text, "test.md", mock_provider, [])
        assert result == []
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_source_line_set_correctly(self, mock_provider: AsyncMock) -> None:
        """The source_line on returned items matches the paragraph start."""
        text = "Heading paragraph\n\nI should really book a flight to SF for the conference."
        mock_provider.complete = AsyncMock(side_effect=["not_action_item", "action_item"])

        result = await detect_implicit_todos(text, "notes/test.md", mock_provider, [])
        assert len(result) == 1
        assert result[0].source_line == 3
        assert result[0].source_file == "notes/test.md"
