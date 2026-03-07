"""Diff logic — reconcile newly parsed TODOs against the store.

On each file change the extractor re-parses the file and calls
:func:`sync_file_todos` to update the store:

- **New TODOs** (no matching store entry) → added to the store.
- **Unchanged TODOs** (text + line match) → left as-is.
- **Updated TODOs** (same text, different line or context) → updated in place.
- **Removed TODOs** (in store but no longer in file) → marked done.
- **File deleted** → all open TODOs for that file are marked done.

Matching heuristic: Two items refer to the "same" TODO if they share the
same ``source_file`` and their ``text`` is equal (case-sensitive).  This is
intentionally simple — a future enhancement could use fuzzy matching.
"""

from __future__ import annotations

from src.common.logging import get_logger
from src.common.store import TodoStore
from src.common.todo_models import TodoItem

logger = get_logger(__name__)


def sync_file_todos(
    store: TodoStore,
    source_file: str,
    new_items: list[TodoItem],
) -> tuple[int, int, int]:
    """Reconcile parsed TODO items for *source_file* against the store.

    This mutates *store* in memory — the caller is responsible for calling
    ``store.save()`` afterwards.

    Args:
        store: The in-memory TODO store.
        source_file: File path relative to ``notes_dir``.
        new_items: The freshly parsed TODO items for this file.

    Returns:
        A tuple of ``(added, updated, marked_done)`` counts.
    """
    existing = store.get_by_file(source_file)

    # Index existing items by text for matching
    existing_by_text: dict[str, list[TodoItem]] = {}
    for item in existing:
        existing_by_text.setdefault(item.text, []).append(item)

    # Track which existing item ids were matched
    matched_ids: set[str] = set()
    added = 0
    updated = 0

    for new_item in new_items:
        candidates = existing_by_text.get(new_item.text, [])
        # Try to find an unmatched existing item with the same text
        match: TodoItem | None = None
        for candidate in candidates:
            if candidate.id not in matched_ids:
                match = candidate
                break

        if match is not None:
            matched_ids.add(match.id)
            # Check if anything changed that warrants an update
            needs_update = (
                match.source_line != new_item.source_line
                or match.surrounding_context != new_item.surrounding_context
                or match.detection_method != new_item.detection_method
                or match.raw_checkbox_state != new_item.raw_checkbox_state
            )
            # If the checkbox was checked, mark done
            if new_item.raw_checkbox_state is True and match.status == "open":
                store.mark_done(match.id)
                updated += 1
            # If the checkbox was unchecked, reopen
            elif (
                new_item.raw_checkbox_state is False
                and match.status == "done"
                and match.raw_checkbox_state is True
            ):
                store.update(
                    match.id,
                    status="open",
                    done_at=None,
                    source_line=new_item.source_line,
                    surrounding_context=new_item.surrounding_context,
                    raw_checkbox_state=new_item.raw_checkbox_state,
                )
                updated += 1
            elif needs_update:
                store.update(
                    match.id,
                    source_line=new_item.source_line,
                    surrounding_context=new_item.surrounding_context,
                    detection_method=new_item.detection_method,
                    raw_checkbox_state=new_item.raw_checkbox_state,
                )
                updated += 1
        else:
            # New TODO — add to store
            store.add(new_item)
            added += 1

    # Mark unmatched open existing items as done (they were removed from the file)
    marked_done = 0
    for item in existing:
        if item.id not in matched_ids and item.status == "open":
            store.mark_done(item.id)
            marked_done += 1

    logger.debug(
        "Synced %s: +%d added, ~%d updated, -%d marked done",
        source_file,
        added,
        updated,
        marked_done,
    )
    return added, updated, marked_done


def mark_file_deleted(store: TodoStore, source_file: str) -> int:
    """Mark all open TODOs for a deleted file as done.

    Args:
        store: The in-memory TODO store.
        source_file: File path relative to ``notes_dir``.

    Returns:
        Number of items marked done.
    """
    open_items = store.get_open_by_file(source_file)
    for item in open_items:
        store.mark_done(item.id)

    if open_items:
        logger.debug(
            "Marked %d TODOs as done for deleted file %s",
            len(open_items),
            source_file,
        )
    return len(open_items)
