"""Unit tests for the regex-based TODO detector."""

from pathlib import Path

import pytest

from src.extractor.regex_detector import detect_todos, detect_todos_in_file

# ---------------------------------------------------------------------------
# Checkbox detection
# ---------------------------------------------------------------------------


class TestCheckboxDetection:
    def test_open_checkbox(self) -> None:
        md = "- [ ] Buy groceries"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Buy groceries"
        assert items[0].detection_method == "checkbox"
        assert items[0].status == "open"
        assert items[0].raw_checkbox_state is False

    def test_checked_checkbox(self) -> None:
        md = "- [x] Buy groceries"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].status == "done"
        assert items[0].raw_checkbox_state is True

    def test_checked_checkbox_uppercase_x(self) -> None:
        md = "- [X] Buy groceries"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].status == "done"
        assert items[0].raw_checkbox_state is True

    def test_multiple_checkboxes(self) -> None:
        md = """# My List

- [ ] First task
- [x] Second task (done)
- [ ] Third task
"""
        items = detect_todos(md, "test.md")
        assert len(items) == 3
        assert items[0].text == "First task"
        assert items[0].status == "open"
        assert items[1].text == "Second task (done)"
        assert items[1].status == "done"
        assert items[2].text == "Third task"
        assert items[2].status == "open"

    def test_nested_checkbox(self) -> None:
        md = "  - [ ] Nested task"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Nested task"

    def test_deeply_nested_checkbox(self) -> None:
        md = "      - [ ] Very nested task"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Very nested task"

    def test_checkbox_with_extra_whitespace(self) -> None:
        md = "- [ ]   Buy  groceries  "
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Buy  groceries"

    def test_not_a_checkbox_no_space(self) -> None:
        """``-[ ]`` without space after dash is not a valid list item."""
        md = "-[ ] not valid"
        items = detect_todos(md, "test.md")
        assert len(items) == 0

    def test_not_a_checkbox_wrong_brackets(self) -> None:
        md = "- ( ) not valid"
        items = detect_todos(md, "test.md")
        assert len(items) == 0


# ---------------------------------------------------------------------------
# Keyword detection
# ---------------------------------------------------------------------------


class TestKeywordDetection:
    def test_todo_keyword(self) -> None:
        md = "TODO: Fix the login bug"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Fix the login bug"
        assert items[0].detection_method == "keyword"
        assert items[0].status == "open"
        assert items[0].raw_checkbox_state is None

    def test_fixme_keyword(self) -> None:
        md = "FIXME: This is broken"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "This is broken"
        assert items[0].detection_method == "keyword"

    def test_action_keyword(self) -> None:
        md = "ACTION: Send the email"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Send the email"
        assert items[0].detection_method == "keyword"

    def test_case_insensitive_keywords(self) -> None:
        md = """todo: lowercase
Todo: Title case
tOdO: Mixed case
"""
        items = detect_todos(md, "test.md")
        assert len(items) == 3

    def test_keyword_without_space_after_colon(self) -> None:
        md = "TODO:Fix this"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Fix this"

    def test_keyword_inline(self) -> None:
        """Keyword appearing after text on the same line."""
        md = "This needs work TODO: refactor this"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "refactor this"

    def test_keyword_in_comment(self) -> None:
        md = "<!-- TODO: hidden task -->"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "hidden task -->"

    def test_multiple_keywords(self) -> None:
        md = """Some prose.

TODO: First thing to do
More prose here.
FIXME: Something broken
ACTION: Call the client
"""
        items = detect_todos(md, "test.md")
        assert len(items) == 3


# ---------------------------------------------------------------------------
# Mixed detection & deduplication
# ---------------------------------------------------------------------------


class TestMixedDetection:
    def test_checkbox_with_keyword_deduplicates(self) -> None:
        """A checkbox that also contains TODO: should only produce one item."""
        md = "- [ ] TODO: Something to do"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        # Checkbox wins
        assert items[0].detection_method == "checkbox"

    def test_mixed_checkboxes_and_keywords(self) -> None:
        md = """# Notes

- [ ] Buy milk
- [x] Already done

Some paragraph.

TODO: Review the document
FIXME: Off-by-one error
"""
        items = detect_todos(md, "test.md")
        assert len(items) == 4
        methods = [i.detection_method for i in items]
        assert methods.count("checkbox") == 2
        assert methods.count("keyword") == 2

    def test_empty_text(self) -> None:
        items = detect_todos("", "test.md")
        assert items == []

    def test_no_todos(self) -> None:
        md = """# Just a heading

Some normal prose with no action items.

- A regular list item
- Another one
"""
        items = detect_todos(md, "test.md")
        assert items == []


# ---------------------------------------------------------------------------
# Source line and context
# ---------------------------------------------------------------------------


class TestSourceLineAndContext:
    def test_source_line_numbers(self) -> None:
        md = """Line 1
Line 2
- [ ] Task on line 3
Line 4
Line 5
TODO: Task on line 6
"""
        items = detect_todos(md, "test.md")
        assert len(items) == 2
        assert items[0].source_line == 3
        assert items[1].source_line == 6

    def test_surrounding_context(self) -> None:
        md = """Line 1
Line 2
Line 3
- [ ] Task on line 4
Line 5
Line 6
Line 7
"""
        items = detect_todos(md, "test.md", context_window=2)
        assert len(items) == 1
        context = items[0].surrounding_context
        assert "Line 2" in context
        assert "Line 3" in context
        assert "Task on line 4" in context
        assert "Line 5" in context
        assert "Line 6" in context

    def test_context_at_start_of_file(self) -> None:
        md = """- [ ] First line task
Line 2
Line 3
"""
        items = detect_todos(md, "test.md", context_window=2)
        assert len(items) == 1
        context = items[0].surrounding_context
        assert "First line task" in context
        assert "Line 2" in context

    def test_context_at_end_of_file(self) -> None:
        md = """Line 1
Line 2
- [ ] Last task"""
        items = detect_todos(md, "test.md", context_window=2)
        assert len(items) == 1
        context = items[0].surrounding_context
        assert "Line 1" in context
        assert "Line 2" in context
        assert "Last task" in context


# ---------------------------------------------------------------------------
# Source file
# ---------------------------------------------------------------------------


class TestSourceFile:
    def test_source_file_stored(self) -> None:
        md = "- [ ] Task"
        items = detect_todos(md, "2024/06/notes.md")
        assert items[0].source_file == "2024/06/notes.md"


# ---------------------------------------------------------------------------
# detect_todos_in_file (file-reading convenience wrapper)
# ---------------------------------------------------------------------------


class TestDetectTodosInFile:
    def test_reads_file_and_detects(self, tmp_path: Path) -> None:
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        md_file = notes_dir / "test.md"
        md_file.write_text("- [ ] From file\nTODO: Another one\n")

        items = detect_todos_in_file(md_file, notes_dir)
        assert len(items) == 2
        assert items[0].source_file == "test.md"
        assert items[1].source_file == "test.md"

    def test_nested_file_relative_path(self, tmp_path: Path) -> None:
        notes_dir = tmp_path / "notes"
        sub = notes_dir / "2024" / "06"
        sub.mkdir(parents=True)
        md_file = sub / "meeting.md"
        md_file.write_text("- [ ] Follow up\n")

        items = detect_todos_in_file(md_file, notes_dir)
        assert len(items) == 1
        assert items[0].source_file == "2024/06/meeting.md"

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            detect_todos_in_file(tmp_path / "nope.md", tmp_path)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_checkbox_empty_text_after_bracket(self) -> None:
        """``- [ ] `` with nothing after should not match (regex requires .+)."""
        md = "- [ ] "
        items = detect_todos(md, "test.md")
        assert items == []

    def test_keyword_at_end_of_line_no_text(self) -> None:
        """``TODO:`` with nothing after should not match."""
        md = "TODO:"
        items = detect_todos(md, "test.md")
        assert items == []

    def test_keyword_only_whitespace_after(self) -> None:
        """``TODO:   `` with only spaces should not match (text is stripped)."""
        md = "TODO:   "
        items = detect_todos(md, "test.md")
        assert items == []

    def test_code_block_contents_detected(self) -> None:
        """Regex detector doesn't skip code blocks — that's intentional for now.

        A future enhancement could exclude fenced code blocks, but the
        current spec doesn't require it.
        """
        md = """```
- [ ] Inside code block
```
"""
        items = detect_todos(md, "test.md")
        assert len(items) == 1

    def test_unicode_text(self) -> None:
        md = "- [ ] Kaufe Brötchen 🥐"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert "Brötchen" in items[0].text

    def test_very_long_line(self) -> None:
        long_text = "A" * 1000
        md = f"TODO: {long_text}"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert len(items[0].text) == 1000

    def test_windows_line_endings(self) -> None:
        md = "Line 1\r\n- [ ] Task\r\nLine 3\r\n"
        items = detect_todos(md, "test.md")
        assert len(items) == 1
        assert items[0].text == "Task"

    def test_each_item_gets_unique_id(self) -> None:
        md = "- [ ] First\n- [ ] Second\n"
        items = detect_todos(md, "test.md")
        assert len(items) == 2
        assert items[0].id != items[1].id
