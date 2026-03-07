"""Unit tests for the TodoStore class."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.common.store import StoreError, TodoStore
from src.common.todo_models import TodoItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(**overrides: object) -> TodoItem:
    """Create a TodoItem with sensible defaults, allowing overrides."""
    defaults: dict[str, object] = {
        "text": "Buy groceries",
        "source_file": "2024/06/notes.md",
        "source_line": 5,
        "detection_method": "checkbox",
    }
    defaults.update(overrides)
    return TodoItem(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Store: basic CRUD
# ---------------------------------------------------------------------------


class TestStoreAdd:
    def test_add_item(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item = _make_item()
        result = store.add(item)
        assert result.id == item.id
        assert store.count == 1
        assert item.id in store

    def test_add_duplicate_raises(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item = _make_item()
        store.add(item)
        with pytest.raises(StoreError, match="Duplicate item id"):
            store.add(item)


class TestStoreUpdate:
    def test_update_fields(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item = _make_item()
        store.add(item)

        updated = store.update(item.id, text="Buy milk instead")
        assert updated.text == "Buy milk instead"
        assert updated.updated_at > item.updated_at

    def test_update_nonexistent_raises(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        with pytest.raises(StoreError, match="Item not found"):
            store.update("nonexistent-id", text="Nope")


class TestStoreMarkDone:
    def test_mark_done(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item = _make_item()
        store.add(item)

        done = store.mark_done(item.id)
        assert done.status == "done"
        assert done.done_at is not None
        assert done.done_at.tzinfo is not None

    def test_mark_done_nonexistent_raises(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        with pytest.raises(StoreError, match="Item not found"):
            store.mark_done("ghost-id")


class TestStoreRemove:
    def test_remove_item(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item = _make_item()
        store.add(item)
        removed = store.remove(item.id)
        assert removed.id == item.id
        assert store.count == 0

    def test_remove_nonexistent_raises(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        with pytest.raises(StoreError, match="Item not found"):
            store.remove("nope")


# ---------------------------------------------------------------------------
# Store: queries
# ---------------------------------------------------------------------------


class TestStoreQueries:
    def test_get(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item = _make_item()
        store.add(item)
        assert store.get(item.id) is not None
        assert store.get("missing") is None

    def test_get_open(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        open_item = _make_item(text="open one")
        done_item = _make_item(text="done one", status="done")
        store.add(open_item)
        store.add(done_item)

        open_items = store.get_open()
        assert len(open_items) == 1
        assert open_items[0].text == "open one"

    def test_get_done(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        open_item = _make_item(text="open one")
        done_item = _make_item(text="done one", status="done")
        store.add(open_item)
        store.add(done_item)

        done_items = store.get_done()
        assert len(done_items) == 1
        assert done_items[0].text == "done one"

    def test_get_by_file(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item_a = _make_item(source_file="a.md", text="from a")
        item_b = _make_item(source_file="b.md", text="from b")
        store.add(item_a)
        store.add(item_b)

        results = store.get_by_file("a.md")
        assert len(results) == 1
        assert results[0].text == "from a"

    def test_get_open_by_file(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        item_open = _make_item(source_file="a.md", text="open")
        item_done = _make_item(source_file="a.md", text="done", status="done")
        item_other = _make_item(source_file="b.md", text="other")
        store.add(item_open)
        store.add(item_done)
        store.add(item_other)

        results = store.get_open_by_file("a.md")
        assert len(results) == 1
        assert results[0].text == "open"

    def test_open_count(self) -> None:
        store = TodoStore(Path("/tmp/unused.json"))
        store.add(_make_item(text="one"))
        store.add(_make_item(text="two"))
        store.add(_make_item(text="three", status="done"))
        assert store.open_count == 2
        assert store.count == 3
        assert len(store) == 3


# ---------------------------------------------------------------------------
# Store: persistence (save / load round-trip)
# ---------------------------------------------------------------------------


class TestStorePersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store_path = tmp_path / "store" / "todos.json"

        # Save
        store = TodoStore(store_path)
        item = _make_item(text="Persist me")
        store.add(item)
        store.save()

        assert store_path.is_file()

        # Load into a fresh store
        store2 = TodoStore(store_path)
        store2.load()
        assert store2.count == 1

        loaded = store2.get(item.id)
        assert loaded is not None
        assert loaded.text == "Persist me"
        assert loaded.source_file == item.source_file
        assert loaded.detection_method == item.detection_method

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        store = TodoStore(tmp_path / "nope.json")
        store.load()
        assert store.count == 0

    def test_load_empty_file(self, tmp_path: Path) -> None:
        store_path = tmp_path / "empty.json"
        store_path.write_text("")
        store = TodoStore(store_path)
        store.load()
        assert store.count == 0

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        store_path = tmp_path / "bad.json"
        store_path.write_text("{not valid json!!!")
        store = TodoStore(store_path)
        with pytest.raises(StoreError, match="Failed to parse"):
            store.load()

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        store_path = tmp_path / "deeply" / "nested" / "store.json"
        store = TodoStore(store_path)
        store.add(_make_item())
        store.save()
        assert store_path.is_file()

    def test_round_trip_preserves_done_at(self, tmp_path: Path) -> None:
        store_path = tmp_path / "todos.json"
        now = datetime.now(UTC)

        store = TodoStore(store_path)
        item = _make_item(text="done task", status="done", done_at=now)
        store.add(item)
        store.save()

        store2 = TodoStore(store_path)
        store2.load()
        loaded = store2.get(item.id)
        assert loaded is not None
        assert loaded.status == "done"
        assert loaded.done_at is not None

    def test_round_trip_multiple_items(self, tmp_path: Path) -> None:
        store_path = tmp_path / "todos.json"
        store = TodoStore(store_path)

        for i in range(10):
            store.add(_make_item(text=f"Item {i}"))
        store.save()

        store2 = TodoStore(store_path)
        store2.load()
        assert store2.count == 10


# ---------------------------------------------------------------------------
# Store: chaining
# ---------------------------------------------------------------------------


class TestStoreChaining:
    def test_load_returns_self(self, tmp_path: Path) -> None:
        store_path = tmp_path / "todos.json"
        store = TodoStore(store_path)
        result = store.load()
        assert result is store
