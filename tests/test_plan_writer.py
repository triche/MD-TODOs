"""Tests for the Manager agent plan file writer."""

from datetime import date
from pathlib import Path

import pytest

from src.manager.plan_writer import plan_filename, plan_output_path, write_plan

# ---------------------------------------------------------------------------
# plan_filename
# ---------------------------------------------------------------------------


class TestPlanFilename:
    """Tests for plan_filename()."""

    def test_morning(self) -> None:
        assert plan_filename("morning", date(2026, 3, 7)) == "2026-03-07-morning-plan.md"

    def test_afternoon(self) -> None:
        assert plan_filename("afternoon", date(2026, 3, 7)) == "2026-03-07-afternoon-plan.md"

    def test_weekly_review(self) -> None:
        assert plan_filename("weekly-review", date(2026, 3, 6)) == "2026-03-06-weekly-review.md"

    def test_weekly_plan(self) -> None:
        assert plan_filename("weekly-plan", date(2026, 3, 8)) == "2026-03-08-weekly-plan.md"

    def test_defaults_to_today(self) -> None:
        result = plan_filename("morning")
        today = date.today()
        assert result.startswith(today.isoformat())
        assert result.endswith("-morning-plan.md")


# ---------------------------------------------------------------------------
# plan_output_path
# ---------------------------------------------------------------------------


class TestPlanOutputPath:
    """Tests for plan_output_path()."""

    def test_creates_year_month_structure(self, tmp_path: Path) -> None:
        result = plan_output_path(tmp_path, "morning", date(2026, 3, 7))
        assert result == tmp_path / "2026" / "03" / "2026-03-07-morning-plan.md"

    def test_single_digit_month_is_zero_padded(self, tmp_path: Path) -> None:
        result = plan_output_path(tmp_path, "afternoon", date(2025, 1, 5))
        assert result == tmp_path / "2025" / "01" / "2025-01-05-afternoon-plan.md"

    def test_december(self, tmp_path: Path) -> None:
        result = plan_output_path(tmp_path, "weekly-plan", date(2025, 12, 28))
        assert result == tmp_path / "2025" / "12" / "2025-12-28-weekly-plan.md"


# ---------------------------------------------------------------------------
# write_plan
# ---------------------------------------------------------------------------


class TestWritePlan:
    """Tests for write_plan()."""

    def test_writes_content_to_correct_path(self, tmp_plans_dir: Path) -> None:
        content = "# Morning Plan\n\nHello world."
        result = write_plan(tmp_plans_dir, "morning", content, date(2026, 3, 7))
        expected = tmp_plans_dir / "2026" / "03" / "2026-03-07-morning-plan.md"
        assert result == expected
        assert result.read_text(encoding="utf-8") == content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        plans_dir = tmp_path / "nonexistent" / "plans"
        content = "# Plan"
        result = write_plan(plans_dir, "afternoon", content, date(2026, 6, 15))
        assert result.exists()
        assert result.read_text(encoding="utf-8") == content

    @pytest.mark.parametrize(
        "plan_type,suffix",
        [
            ("morning", "morning-plan"),
            ("afternoon", "afternoon-plan"),
            ("weekly-review", "weekly-review"),
            ("weekly-plan", "weekly-plan"),
        ],
    )
    def test_all_plan_types_write_correctly(
        self, tmp_plans_dir: Path, plan_type: str, suffix: str
    ) -> None:
        d = date(2026, 3, 7)
        content = f"# {plan_type} plan"
        result = write_plan(tmp_plans_dir, plan_type, content, d)  # type: ignore[arg-type]
        assert result.name == f"2026-03-07-{suffix}.md"
        assert result.read_text(encoding="utf-8") == content

    def test_overwrites_existing_plan(self, tmp_plans_dir: Path) -> None:
        d = date(2026, 3, 7)
        write_plan(tmp_plans_dir, "morning", "Old content", d)
        result = write_plan(tmp_plans_dir, "morning", "New content", d)
        assert result.read_text(encoding="utf-8") == "New content"
