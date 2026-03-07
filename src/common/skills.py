"""Loader utility for the GTD skills file.

The skills file (``skills/gtd.md``) is injected into the LLM system prompt so
the Manager agent understands GTD methodology without hard-coding the logic.
This module provides a single function to load and validate the file.
"""

from pathlib import Path

from src.common.logging import get_logger

logger = get_logger(__name__)

# The default skills path is relative to the repo root.  At runtime the
# installer writes an absolute path into config.yaml so this fallback is
# only used during development / testing.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SKILLS_PATH = _REPO_ROOT / "skills" / "gtd.md"


class SkillsFileError(Exception):
    """Raised when the skills file cannot be loaded."""


def load_skills(skills_path: Path | None = None) -> str:
    """Load the GTD skills Markdown file and return its content.

    Args:
        skills_path: Explicit path to the skills file.  Falls back to the
            repo-relative default (``skills/gtd.md``) when *None*.

    Returns:
        The full text of the skills file.

    Raises:
        SkillsFileError: If the file does not exist, is not a file, or is
            empty.
    """
    path = (skills_path or DEFAULT_SKILLS_PATH).expanduser().resolve()

    if not path.exists():
        msg = f"Skills file not found: {path}"
        raise SkillsFileError(msg)

    if not path.is_file():
        msg = f"Skills path is not a file: {path}"
        raise SkillsFileError(msg)

    content = path.read_text(encoding="utf-8")

    if not content.strip():
        msg = f"Skills file is empty: {path}"
        raise SkillsFileError(msg)

    logger.debug("Loaded skills file from %s (%d chars)", path, len(content))
    return content
