"""Plan file writer for the Manager agent.

Resolves output paths under ``plans_dir/<YYYY>/<MM>/<filename>.md`` and
writes generated Markdown plans to disk, creating directories as needed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.manager.prompt_builder import PlanType

logger = get_logger(__name__)

# Mapping from plan type to the filename suffix used in the output file.
_PLAN_TYPE_SUFFIXES: dict[PlanType, str] = {
    "morning": "morning-plan",
    "afternoon": "afternoon-plan",
    "weekly-review": "weekly-review",
    "weekly-plan": "weekly-plan",
}


def plan_filename(plan_type: PlanType, plan_date: date | None = None) -> str:
    """Return the filename for a plan.

    Format: ``YYYY-MM-DD-<suffix>.md``

    Args:
        plan_type: The type of plan being generated.
        plan_date: The date for the plan.  Defaults to today.

    Returns:
        The plan filename (no directory component).
    """
    d = plan_date or date.today()
    suffix = _PLAN_TYPE_SUFFIXES[plan_type]
    return f"{d.isoformat()}-{suffix}.md"


def plan_output_path(
    plans_dir: Path,
    plan_type: PlanType,
    plan_date: date | None = None,
) -> Path:
    """Resolve the full output path for a plan file.

    Path format: ``<plans_dir>/<YYYY>/<MM>/<YYYY-MM-DD-<suffix>.md>``

    Args:
        plans_dir: Root plans directory from config.
        plan_type: The type of plan being generated.
        plan_date: The date for the plan.  Defaults to today.

    Returns:
        The absolute resolved path to the plan file.
    """
    d = plan_date or date.today()
    year_dir = str(d.year)
    month_dir = f"{d.month:02d}"
    filename = plan_filename(plan_type, d)
    return plans_dir.expanduser().resolve() / year_dir / month_dir / filename


def write_plan(
    plans_dir: Path,
    plan_type: PlanType,
    content: str,
    plan_date: date | None = None,
) -> Path:
    """Write a generated plan to disk.

    Creates parent directories as needed.

    Args:
        plans_dir: Root plans directory from config.
        plan_type: The type of plan that was generated.
        content: The Markdown content of the plan.
        plan_date: The date for the plan.  Defaults to today.

    Returns:
        The absolute path to the written file.
    """
    output = plan_output_path(plans_dir, plan_type, plan_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    logger.info("Wrote %s plan to %s", plan_type, output)
    return output
