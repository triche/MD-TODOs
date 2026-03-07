"""Unit tests for the diff / sync logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.store import TodoStore
from src.common.todo_models import TodoItem
from src.extractor.diff import mark_file_deleted, sync_file_todos


@pytest.fixture
def store(tmp_path: Path) -> TodoStore:
    """Create an empty in-memory store."""
    return TodoStore(tmp_path / "store" / "todos.json")


def _make_item(
    text: str,
    source_file: str = "test.md",
    source_line: int = 1,
    detection_method: str = "checkbox",
    status: str = "open",
    raw_checkbox_state: bool | None = False,
) -> TodoItem:
    return TodoItem(
        text=text,
        source_file=source_file,
        source_line=source_line,
        detection_method=detection_method,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        raw_checkbox_state=raw_checkbox_state,
    )


class TestSyncFileTodos:
    def test_add_new_items(self, store: TodoStore) -> None:
        """New items not in the store are added."""
        new_items = [
            _make_item("Buy milk", source_line=1),
            _make_item("Fix bug", source_line=5, detection_method="keyword"),
        ]
        added, updated, done = sync_file_todos(store, "test.md", new_items)
        assert added == 2
        assert updated == 0
        assert done == 0
        assert store.count == 2

    def test_unchanged_items_not_duplicated(self, store: TodoStore) -> None:
        """Items that already exist with matching text are not added again."""
        existing = _make_item("Buy milk", source_line=1)
        store.add(existing)

        new_items = [_make_item("Buy milk", source_line=1)]
        added, updated, done = sync_file_todos(store, "test.md", new_items)
        assert added == 0
        assert updated == 0
        assert done == 0
        assert store.count == 1

    def test_item_moved_to_different_line(self, store: TodoStore) -> None:
        """When text matches but line changed, the item is updated."""
        existing = _make_item("Buy milk", source_line=1)
        store.add(existing)

        new_items = [_make_item("Buy milk", source_line=5)]
        added, updated, done = sync_file_todos(store, "test.md", new_items)
        assert added == 0
        assert updated == 1
        assert done == 0

        stored = store.get_by_file("test.md")
        assert len(stored) == 1
        assert stored[0].source_line == 5

    def test_removed_item_marked_done(self, store: TodoStore) -> None:
        """Open items no longer in the file are marked done."""
        existing = _make_item("Buy milk", source_line=1)
        store.add(existing)

        # Parse returns no items → the existing one is removed
        added, updated, done = sync_file_todos(store, "test.md", [])
        assert added == 0
        assert updated == 0
        assert done == 1

        stored = store.get_by_file("test.md")
        assert len(stored) == 1
        assert stored[0].status == "done"

    def test_already_done_item_not_re_marked(self, store: TodoStore) -> None:
        """Items already marked done are not affected by removal."""
        existing = _make_item("Buy milk", source_line=1, status="done")
        # Need to set raw_checkbox_state=True to trigger done status properly
        existing = existing.model_copy(update={"status": "done"})
        store.add(existing)

        _added, _updated, done = sync_file_todos(store, "test.md", [])
        # Already done, so not counted again
        assert done == 0

    def test_checkbox_checked_marks_done(self, store: TodoStore) -> None:
        """When a checkbox changes from unchecked to checked, mark done."""
        existing = _make_item("Buy milk", source_line=1, raw_checkbox_state=False)
        store.add(existing)

        new_items = [_make_item("Buy milk", source_line=1, raw_checkbox_state=True)]
        _added, updated, _done = sync_file_todos(store, "test.md", new_items)
        assert updated == 1

        stored = store.get_by_file("test.md")
        assert stored[0].status == "done"

    def test_checkbox_unchecked_reopens(self, store: TodoStore) -> None:
        """When a checkbox is unchecked, the item is reopened."""
        existing = _make_item("Buy milk", source_line=1, status="done", raw_checkbox_state=True)
        existing = existing.model_copy(update={"status": "done"})
        store.add(existing)

        new_items = [_make_item("Buy milk", source_line=1, raw_checkbox_state=False)]
        _added, updated, done = sync_file_todos(store, "test.md", new_items)
        assert updated == 1
        assert done == 0

        stored = store.get_by_file("test.md")
        assert stored[0].status == "open"

    def test_different_files_independent(self, store: TodoStore) -> None:
        """Syncing one file doesn't affect items from another file."""
        item_a = _make_item("Buy milk", source_file="a.md", source_line=1)
        item_b = _make_item("Fix bug", source_file="b.md", source_line=1)
        store.add(item_a)
        store.add(item_b)

        # Sync a.md with no items → marks a.md's item done
        _added, _updated, done = sync_file_todos(store, "a.md", [])
        assert done == 1

        # b.md's item is untouched
        b_items = store.get_by_file("b.md")
        assert len(b_items) == 1
        assert b_items[0].status == "open"

    def test_multiple_items_same_text(self, store: TodoStore) -> None:
        """Handle duplicate texts (e.g. same task mentioned twice)."""
        existing1 = _make_item("Buy milk", source_line=1)
        existing2 = _make_item("Buy milk", source_line=5)
        store.add(existing1)
        store.add(existing2)

        # Both still present
        new_items = [
            _make_item("Buy milk", source_line=2),
            _make_item("Buy milk", source_line=6),
        ]
        added, updated, done = sync_file_todos(store, "test.md", new_items)
        assert added == 0
        assert updated == 2  # both moved lines
        assert done == 0

    def test_add_and_remove_same_sync(self, store: TodoStore) -> None:
        """Add new items and remove old ones in a single sync."""
        old = _make_item("Old task", source_line=1)
        store.add(old)

        new_items = [_make_item("New task", source_line=3)]
        added, _updated, done = sync_file_todos(store, "test.md", new_items)
        assert added == 1
        assert done == 1
        assert store.count == 2  # old (done) + new


class TestMarkFileDeleted:
    def test_marks_open_items_done(self, store: TodoStore) -> None:
        item1 = _make_item("Task 1", source_file="deleted.md", source_line=1)
        item2 = _make_item("Task 2", source_file="deleted.md", source_line=3)
        store.add(item1)
        store.add(item2)

        count = mark_file_deleted(store, "deleted.md")
        assert count == 2
        assert all(i.status == "done" for i in store.get_by_file("deleted.md"))

    def test_already_done_items_not_affected(self, store: TodoStore) -> None:
        item = _make_item("Done task", source_file="deleted.md", source_line=1, status="done")
        item = item.model_copy(update={"status": "done"})
        store.add(item)

        count = mark_file_deleted(store, "deleted.md")
        assert count == 0

    def test_no_items_for_file(self, store: TodoStore) -> None:
        count = mark_file_deleted(store, "nonexistent.md")
        assert count == 0

    def test_only_target_file_affected(self, store: TodoStore) -> None:
        item_a = _make_item("Task A", source_file="keep.md", source_line=1)
        item_b = _make_item("Task B", source_file="deleted.md", source_line=1)
        store.add(item_a)
        store.add(item_b)

        mark_file_deleted(store, "deleted.md")
        assert store.get_by_file("keep.md")[0].status == "open"
        assert store.get_by_file("deleted.md")[0].status == "done"
