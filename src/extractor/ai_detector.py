"""AI-based implicit TODO detector.

Sends paragraphs of Markdown text (that were *not* already captured by the
regex detector) to the AI provider for classification.  Paragraphs classified
as containing an implicit action item are returned as ``TodoItem`` instances
with ``detection_method="ai_implicit"``.
"""

from __future__ import annotations

import asyncio
import re

from src.ai.provider import AIProvider, AIProviderError
from src.common.logging import get_logger
from src.common.todo_models import TodoItem

logger = get_logger(__name__)

# Categories used for the classify call
_CATEGORIES = ["action_item", "not_action_item"]

# Minimum paragraph length (in characters) to bother sending to the LLM.
_MIN_PARAGRAPH_LEN = 15


def _split_paragraphs(text: str) -> list[tuple[str, int]]:
    """Split *text* into paragraphs and return each with its 1-based start line.

    A paragraph is a block of non-empty lines separated by one or more blank
    lines.  Returns a list of ``(paragraph_text, start_line_1based)`` tuples.
    """
    paragraphs: list[tuple[str, int]] = []
    lines = text.split("\n")
    current_lines: list[str] = []
    start_line = 1

    for idx, line in enumerate(lines):
        if line.strip():
            if not current_lines:
                start_line = idx + 1  # 1-based
            current_lines.append(line)
        else:
            if current_lines:
                paragraphs.append(("\n".join(current_lines), start_line))
                current_lines = []

    # Flush any trailing paragraph
    if current_lines:
        paragraphs.append(("\n".join(current_lines), start_line))

    return paragraphs


def _lines_already_covered(regex_items: list[TodoItem]) -> set[int]:
    """Build a set of 1-based line numbers already detected by regex."""
    return {item.source_line for item in regex_items}


def _paragraph_overlaps_regex(
    para_start: int,
    para_text: str,
    covered: set[int],
) -> bool:
    """Return *True* if any line of the paragraph was already detected."""
    para_lines = para_text.count("\n") + 1
    return any((para_start + offset) in covered for offset in range(para_lines))


def _surrounding_context(lines: list[str], line_idx: int, window: int = 2) -> str:
    """Return up to *window* lines above and below *line_idx* (0-based)."""
    start = max(0, line_idx - window)
    end = min(len(lines), line_idx + window + 1)
    return "\n".join(lines[start:end])


def _extract_action_text(paragraph: str) -> str:
    """Extract a concise action-item description from a paragraph.

    If the paragraph is short enough, return it verbatim (stripped).
    Otherwise return the first sentence.
    """
    stripped = paragraph.strip()
    # Collapse whitespace
    stripped = re.sub(r"\s+", " ", stripped)
    if len(stripped) <= 120:
        return stripped
    # Take first sentence
    match = re.match(r"(.+?[.!?])\s", stripped)
    if match:
        return match.group(1)
    return stripped[:120] + "…"


async def detect_implicit_todos(
    text: str,
    source_file: str,
    provider: AIProvider,
    regex_items: list[TodoItem],
    *,
    context_window: int = 2,
) -> list[TodoItem]:
    """Detect implicit TODOs in paragraphs not captured by regex.

    Args:
        text: Raw Markdown content of a single file.
        source_file: Path relative to ``notes_dir``.
        provider: The AI provider to use for classification.
        regex_items: TODO items already detected by the regex detector
            (used to skip paragraphs that overlap known TODOs).
        context_window: Lines of context above/below for ``surrounding_context``.

    Returns:
        A list of ``TodoItem`` instances with ``detection_method="ai_implicit"``.
    """
    paragraphs = _split_paragraphs(text)
    covered = _lines_already_covered(regex_items)
    lines = text.splitlines()

    # Filter to paragraphs worth classifying
    candidates: list[tuple[str, int]] = []
    for para_text, para_start in paragraphs:
        if len(para_text.strip()) < _MIN_PARAGRAPH_LEN:
            continue
        if _paragraph_overlaps_regex(para_start, para_text, covered):
            continue
        candidates.append((para_text, para_start))

    if not candidates:
        logger.debug("No candidate paragraphs for AI detection in %s", source_file)
        return []

    logger.debug(
        "Sending %d candidate paragraphs to AI for %s",
        len(candidates),
        source_file,
    )

    items: list[TodoItem] = []

    for para_text, para_start in candidates:
        try:
            category = await provider.classify(para_text, _CATEGORIES)
        except AIProviderError:
            logger.warning(
                "AI classification failed for paragraph at line %d in %s; skipping",
                para_start,
                source_file,
                exc_info=True,
            )
            continue

        if category == "action_item":
            line_idx = para_start - 1  # 0-based
            context = _surrounding_context(lines, line_idx, window=context_window)
            action_text = _extract_action_text(para_text)

            item = TodoItem(
                text=action_text,
                source_file=source_file,
                source_line=para_start,
                surrounding_context=context,
                detection_method="ai_implicit",
                status="open",
            )
            items.append(item)
            logger.debug(
                "AI detected implicit TODO at line %d in %s: %s",
                para_start,
                source_file,
                action_text[:60],
            )

    logger.debug(
        "AI detection found %d implicit TODOs in %s",
        len(items),
        source_file,
    )
    return items


def detect_implicit_todos_sync(
    text: str,
    source_file: str,
    provider: AIProvider,
    regex_items: list[TodoItem],
    *,
    context_window: int = 2,
) -> list[TodoItem]:
    """Synchronous wrapper around :func:`detect_implicit_todos`.

    Runs the async function in the current event loop if one exists,
    otherwise creates a new one.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an already-running event loop (e.g. Jupyter, tests).
        # Create a new loop in a thread to avoid nesting.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                detect_implicit_todos(
                    text,
                    source_file,
                    provider,
                    regex_items,
                    context_window=context_window,
                ),
            )
            return future.result()
    else:
        return asyncio.run(
            detect_implicit_todos(
                text,
                source_file,
                provider,
                regex_items,
                context_window=context_window,
            )
        )
