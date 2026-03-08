"""Tests for the Manager agent prompt builder."""

import pytest

from src.common.todo_models import TodoItem
from src.manager.prompt_builder import (
    ALL_PLAN_TYPES,
    build_system_prompt,
    build_user_prompt,
    get_plan_instructions,
)

# ---------------------------------------------------------------------------
# get_plan_instructions
# ---------------------------------------------------------------------------


class TestGetPlanInstructions:
    """Tests for get_plan_instructions()."""

    @pytest.mark.parametrize("plan_type", ALL_PLAN_TYPES)
    def test_returns_instructions_for_valid_types(self, plan_type: str) -> None:
        result = get_plan_instructions(plan_type)  # type: ignore[arg-type]
        assert isinstance(result, str)
        assert len(result) > 100  # substantive instructions

    def test_morning_includes_key_sections(self) -> None:
        result = get_plan_instructions("morning")
        assert "Top 3 Priorities" in result
        assert "Quick Wins" in result
        assert "Context" in result

    def test_afternoon_includes_key_sections(self) -> None:
        result = get_plan_instructions("afternoon")
        assert "Quick Wins" in result or "Remaining Quick Wins" in result
        assert "Defer" in result
        assert "Delegation" in result

    def test_weekly_review_includes_key_sections(self) -> None:
        result = get_plan_instructions("weekly-review")
        assert "Get Clear" in result
        assert "Get Current" in result
        assert "Get Creative" in result
        assert "completed since" in result.lower() or "Completed" in result

    def test_weekly_plan_includes_key_sections(self) -> None:
        result = get_plan_instructions("weekly-plan")
        assert "Weekend Review" in result
        assert "Day-by-Day" in result
        assert "Quadrant 2" in result
        assert "weekend" in result.lower()

    def test_unknown_plan_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown plan type"):
            get_plan_instructions("invalid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Tests for build_system_prompt()."""

    def test_combines_skills_and_instructions(self) -> None:
        skills = "# GTD Reference\nSome GTD content here."
        result = build_system_prompt(skills, "morning")
        assert skills in result
        assert "Morning Plan" in result
        assert "---" in result  # separator between skills and instructions

    @pytest.mark.parametrize("plan_type", ALL_PLAN_TYPES)
    def test_all_plan_types_produce_system_prompt(self, plan_type: str) -> None:
        skills = "# GTD Skills"
        result = build_system_prompt(skills, plan_type)  # type: ignore[arg-type]
        assert "# GTD Skills" in result
        assert len(result) > len(skills)


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------


def _make_todo(text: str = "Test TODO", source_file: str = "notes.md", line: int = 1) -> TodoItem:
    return TodoItem(
        text=text,
        source_file=source_file,
        source_line=line,
        detection_method="checkbox",
    )


class TestBuildUserPrompt:
    """Tests for build_user_prompt()."""

    def test_empty_todos_returns_empty_inbox_message(self) -> None:
        result = build_user_prompt([])
        assert "no open todo items" in result.lower()
        assert "Someday/Maybe" in result

    def test_single_todo_includes_json(self) -> None:
        todos = [_make_todo("Buy groceries")]
        result = build_user_prompt(todos)
        assert "1 total" in result
        assert "Buy groceries" in result
        assert "```json" in result

    def test_multiple_todos_includes_count(self) -> None:
        todos = [_make_todo(f"Item {i}") for i in range(5)]
        result = build_user_prompt(todos)
        assert "5 total" in result

    def test_json_is_parseable(self) -> None:
        import json

        todos = [_make_todo("Test item", "project/notes.md", 42)]
        result = build_user_prompt(todos)
        # Extract JSON block
        start = result.index("```json\n") + len("```json\n")
        end = result.index("\n```", start)
        json_str = result[start:end]
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["text"] == "Test item"
        assert parsed[0]["source_file"] == "project/notes.md"
        assert parsed[0]["source_line"] == 42

    def test_completed_todos_included(self) -> None:
        open_todos = [_make_todo("Open item")]
        completed = [_make_todo("Done item")]
        result = build_user_prompt(open_todos, completed_todos=completed)
        assert "1 total" in result
        assert "Open item" in result
        assert "recently completed" in result.lower()
        assert "Done item" in result

    def test_completed_todos_without_open(self) -> None:
        result = build_user_prompt([], completed_todos=[_make_todo("Finished")])
        assert "no open todo items" in result.lower()
        assert "Finished" in result
        assert "recently completed" in result.lower()

    def test_no_completed_section_when_none(self) -> None:
        result = build_user_prompt([_make_todo("Open")])
        assert "recently completed" not in result.lower()

    def test_no_completed_section_when_empty_list(self) -> None:
        result = build_user_prompt([_make_todo("Open")], completed_todos=[])
        assert "recently completed" not in result.lower()
