"""Markdown file parser — combines regex and AI detection.

Reads a Markdown file, runs the cheap regex detector first, then
optionally sends uncaptured paragraphs to the AI provider for
implicit-TODO classification.  Returns a unified list of ``TodoItem``
instances.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.ai.provider import AIProvider, AIProviderError
from src.common.logging import get_logger
from src.common.todo_models import TodoItem
from src.extractor.ai_detector import detect_implicit_todos
from src.extractor.regex_detector import detect_todos

logger = get_logger(__name__)


async def parse_file_async(
    file_path: Path,
    notes_dir: Path,
    *,
    provider: AIProvider | None = None,
    implicit_detection: bool = True,
    context_window: int = 2,
) -> list[TodoItem]:
    """Parse a single Markdown file and return all detected TODOs.

    The function:
    1. Reads the file content.
    2. Runs the regex detector (checkboxes + keywords).
    3. If *implicit_detection* is enabled and a *provider* is available,
       sends remaining paragraphs to the AI for implicit-TODO classification.
    4. Returns the combined, deduplicated list sorted by line number.

    Args:
        file_path: Absolute path to the Markdown file.
        notes_dir: Absolute path to the notes root directory.
        provider: Optional AI provider for implicit detection.
        implicit_detection: Whether to use AI classification.
        context_window: Lines of context above/below for surrounding_context.

    Returns:
        A sorted list of ``TodoItem`` instances.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
    """
    file_path = file_path.resolve()
    notes_dir = notes_dir.resolve()

    if not file_path.is_file():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    text = file_path.read_text(encoding="utf-8")

    # Compute relative source path
    try:
        relative = file_path.relative_to(notes_dir)
    except ValueError:
        relative = file_path
    source_file = str(relative)

    # Step 1: Regex detection (cheap, fast)
    regex_items = detect_todos(text, source_file, context_window=context_window)

    # Step 2: AI implicit detection (only if enabled and provider available)
    ai_items: list[TodoItem] = []
    if implicit_detection and provider is not None:
        try:
            ai_items = await detect_implicit_todos(
                text,
                source_file,
                provider,
                regex_items,
                context_window=context_window,
            )
        except AIProviderError:
            logger.warning(
                "AI detection failed for %s; using regex results only",
                source_file,
                exc_info=True,
            )

    # Combine and sort by line number
    all_items = regex_items + ai_items
    all_items.sort(key=lambda item: item.source_line)

    logger.debug(
        "Parsed %s: %d regex + %d AI = %d total TODOs",
        source_file,
        len(regex_items),
        len(ai_items),
        len(all_items),
    )
    return all_items


def parse_file(
    file_path: Path,
    notes_dir: Path,
    *,
    provider: AIProvider | None = None,
    implicit_detection: bool = True,
    context_window: int = 2,
) -> list[TodoItem]:
    """Synchronous wrapper around :func:`parse_file_async`.

    Safe to call from synchronous code — creates or reuses an event loop
    as needed.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                parse_file_async(
                    file_path,
                    notes_dir,
                    provider=provider,
                    implicit_detection=implicit_detection,
                    context_window=context_window,
                ),
            )
            return future.result()
    else:
        return asyncio.run(
            parse_file_async(
                file_path,
                notes_dir,
                provider=provider,
                implicit_detection=implicit_detection,
                context_window=context_window,
            )
        )
