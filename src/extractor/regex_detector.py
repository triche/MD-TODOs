"""Regex-based TODO detector for Markdown files.

Detects three kinds of TODOs:

1. **Checkboxes** — ``- [ ] task`` (open) and ``- [x] task`` (done).
2. **Keywords** — lines containing ``TODO:``, ``FIXME:``, or ``ACTION:``.
3. (Future) AI-based implicit detection is handled separately.

The detector operates on raw Markdown text and returns a list of
``TodoItem`` instances with ``detection_method``, ``source_line``,
and ``surrounding_context`` populated.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from src.common.logging import get_logger
from src.common.todo_models import TodoItem

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Markdown checkbox: ``- [ ] text`` or ``- [x] text`` (case-insensitive x)
# Optional leading whitespace for nested lists.
_CHECKBOX_RE = re.compile(
    r"^(?P<indent>\s*)-\s+\[(?P<state>[ xX])\]\s+(?P<text>.+)$",
    re.MULTILINE,
)

# Keyword markers: ``TODO:``, ``FIXME:``, ``ACTION:`` (case-insensitive)
# Captures everything after the keyword on the same line.
_KEYWORD_RE = re.compile(
    r"(?:^|(?<=\s))(?P<keyword>TODO|FIXME|ACTION)\s*:\s*(?P<text>.+)",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RawMatch:
    """Intermediate detection result before conversion to TodoItem."""

    text: str
    line_number: int  # 1-based
    detection_method: str  # "checkbox" or "keyword"
    raw_checkbox_state: bool | None  # None for keyword matches


def _surrounding_context(lines: list[str], line_idx: int, window: int = 2) -> str:
    """Return up to *window* lines above and below *line_idx*, joined.

    Args:
        lines: All lines of the file (0-indexed).
        line_idx: 0-based index of the target line.
        window: Number of context lines above and below.
    """
    start = max(0, line_idx - window)
    end = min(len(lines), line_idx + window + 1)
    return "\n".join(lines[start:end])


def _detect_checkboxes(text: str) -> list[_RawMatch]:
    """Find all Markdown checkboxes in *text*."""
    results: list[_RawMatch] = []
    for match in _CHECKBOX_RE.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        state_char = match.group("state")
        checked = state_char.lower() == "x"
        results.append(
            _RawMatch(
                text=match.group("text").strip(),
                line_number=line_number,
                detection_method="checkbox",
                raw_checkbox_state=checked,
            )
        )
    return results


def _detect_keywords(text: str) -> list[_RawMatch]:
    """Find all keyword-based TODOs (TODO:, FIXME:, ACTION:) in *text*."""
    results: list[_RawMatch] = []
    for match in _KEYWORD_RE.finditer(text):
        stripped_text = match.group("text").strip()
        if not stripped_text:
            continue
        line_number = text.count("\n", 0, match.start()) + 1
        results.append(
            _RawMatch(
                text=stripped_text,
                line_number=line_number,
                detection_method="keyword",
                raw_checkbox_state=None,
            )
        )
    return results


def _deduplicate(matches: list[_RawMatch]) -> list[_RawMatch]:
    """Remove duplicate detections on the same line.

    If a checkbox line also contains a keyword (e.g. ``- [ ] TODO: do X``),
    keep only the checkbox match since it's the more specific detection.
    """
    by_line: dict[int, _RawMatch] = {}
    for m in matches:
        existing = by_line.get(m.line_number)
        if existing is None:
            by_line[m.line_number] = m
        elif m.detection_method == "checkbox":
            # Checkbox wins over keyword on same line
            by_line[m.line_number] = m
    return list(by_line.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_todos(
    text: str,
    source_file: str,
    *,
    context_window: int = 2,
) -> list[TodoItem]:
    """Detect TODOs in Markdown *text* using regex patterns.

    Args:
        text: Raw Markdown content of a single file.
        source_file: Path to the file **relative to notes_dir**
            (stored on each ``TodoItem.source_file``).
        context_window: Number of lines above/below to capture as
            surrounding context.

    Returns:
        A list of ``TodoItem`` instances for every detected TODO.
        Checked checkboxes (``- [x]``) get ``status="done"``.
    """
    checkbox_matches = _detect_checkboxes(text)
    keyword_matches = _detect_keywords(text)

    all_matches = _deduplicate(checkbox_matches + keyword_matches)
    # Sort by line number for deterministic output
    all_matches.sort(key=lambda m: m.line_number)

    lines = text.splitlines()
    items: list[TodoItem] = []

    for raw in all_matches:
        line_idx = raw.line_number - 1  # 0-based for list indexing
        context = _surrounding_context(lines, line_idx, window=context_window)

        status = "open"
        if raw.raw_checkbox_state is True:
            status = "done"

        item = TodoItem(
            text=raw.text,
            source_file=source_file,
            source_line=raw.line_number,
            surrounding_context=context,
            detection_method=raw.detection_method,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            raw_checkbox_state=raw.raw_checkbox_state,
        )
        items.append(item)

    logger.debug(
        "Detected %d TODOs in %s (checkboxes=%d, keywords=%d)",
        len(items),
        source_file,
        len(checkbox_matches),
        len(keyword_matches),
    )
    return items


def detect_todos_in_file(
    file_path: Path,
    notes_dir: Path,
    *,
    context_window: int = 2,
) -> list[TodoItem]:
    """Convenience wrapper: read a file and detect TODOs.

    Args:
        file_path: Absolute path to the Markdown file.
        notes_dir: Absolute path to the notes root directory.
            Used to compute the relative ``source_file``.
        context_window: Number of context lines above/below.

    Returns:
        List of detected ``TodoItem`` instances.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
    """
    file_path = file_path.resolve()
    notes_dir = notes_dir.resolve()

    text = file_path.read_text(encoding="utf-8")

    # Compute path relative to notes_dir (always forward slashes)
    try:
        relative = file_path.relative_to(notes_dir)
    except ValueError:
        # File is outside notes_dir — use the full path as-is
        relative = file_path
    source_file = str(relative)

    return detect_todos(text, source_file, context_window=context_window)
