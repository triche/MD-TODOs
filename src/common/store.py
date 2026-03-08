"""JSON-backed TODO store with file locking.

The extractor agent is the **sole writer** to the store file.  File locking
via ``fcntl.flock`` prevents corruption from concurrent access (e.g. a
manual CLI invocation while the daemon is running).

Store location is resolved from ``AppConfig.store_path``
(default ``~/.md-todos/store/todos.json``).
"""

import fcntl
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pydantic import TypeAdapter

from src.common.logging import get_logger
from src.common.todo_models import TodoItem

logger = get_logger(__name__)

_TODO_LIST_ADAPTER = TypeAdapter(list[TodoItem])


class StoreError(Exception):
    """Raised when the store encounters an unrecoverable error."""


class TodoStore:
    """Manages reading and writing ``TodoItem`` records to a JSON file.

    All public write methods acquire an exclusive file lock to guarantee
    consistency.  Read methods acquire a shared lock so they can run
    concurrently with other readers but not with a writer.

    Usage::

        store = TodoStore(Path("~/.md-todos/store/todos.json"))
        store.load()
        store.add(todo_item)
        store.save()
    """

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()
        self._items: dict[str, TodoItem] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Absolute, resolved path to the store file."""
        return self._path

    @property
    def items(self) -> dict[str, TodoItem]:
        """All items keyed by their UUID."""
        return self._items

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> Self:
        """Load items from the JSON file into memory.

        If the file does not exist or is empty, the store starts empty.
        Returns *self* for chaining.
        """
        if not self._path.is_file():
            logger.debug("Store file does not exist yet: %s", self._path)
            self._items = {}
            return self

        try:
            with self._path.open("r", encoding="utf-8") as fh:
                fcntl.flock(fh, fcntl.LOCK_SH)
                try:
                    raw = fh.read()
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)

            if not raw.strip():
                self._items = {}
                return self

            todo_list = _TODO_LIST_ADAPTER.validate_json(raw)
            self._items = {item.id: item for item in todo_list}
            logger.debug("Loaded %d items from store", len(self._items))
        except (json.JSONDecodeError, ValueError) as exc:
            msg = f"Failed to parse store file {self._path}: {exc}"
            raise StoreError(msg) from exc

        return self

    def save(self) -> None:
        """Persist all in-memory items to the JSON file.

        Creates parent directories if they don't exist.  Acquires an
        exclusive lock for the entire write operation.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        items_list = list(self._items.values())
        data = _TODO_LIST_ADAPTER.dump_json(items_list, indent=2).decode()

        with self._path.open("w", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(data)
                fh.write("\n")
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

        logger.debug("Saved %d items to store", len(self._items))

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def add(self, item: TodoItem) -> TodoItem:
        """Add a new TODO item to the store.

        If an item with the same ``id`` already exists, raises ``StoreError``.
        """
        if item.id in self._items:
            msg = f"Duplicate item id: {item.id}"
            raise StoreError(msg)
        self._items[item.id] = item
        logger.debug("Added item %s: %s", item.id[:8], item.text[:60])
        return item

    def update(self, item_id: str, **fields: object) -> TodoItem:
        """Update one or more fields on an existing item.

        Automatically bumps ``updated_at``.

        Args:
            item_id: UUID of the item to update.
            **fields: Field names and their new values.

        Returns:
            The updated ``TodoItem``.

        Raises:
            StoreError: If the item does not exist.
        """
        existing = self._items.get(item_id)
        if existing is None:
            msg = f"Item not found: {item_id}"
            raise StoreError(msg)

        update_data = {**fields, "updated_at": datetime.now(UTC)}
        updated = existing.model_copy(update=update_data)
        self._items[item_id] = updated
        logger.debug("Updated item %s", item_id[:8])
        return updated

    def mark_done(self, item_id: str) -> TodoItem:
        """Mark an item as done.

        Sets ``status`` to ``"done"`` and records ``done_at``.

        Raises:
            StoreError: If the item does not exist.
        """
        now = datetime.now(UTC)
        return self.update(item_id, status="done", done_at=now)

    def remove(self, item_id: str) -> TodoItem:
        """Remove an item from the store entirely.

        Raises:
            StoreError: If the item does not exist.
        """
        item = self._items.pop(item_id, None)
        if item is None:
            msg = f"Item not found: {item_id}"
            raise StoreError(msg)
        logger.debug("Removed item %s", item_id[:8])
        return item

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get(self, item_id: str) -> TodoItem | None:
        """Return a single item by id, or *None* if not found."""
        return self._items.get(item_id)

    def get_open(self) -> list[TodoItem]:
        """Return all items whose status is ``"open"``."""
        return [item for item in self._items.values() if item.status == "open"]

    def get_done(self) -> list[TodoItem]:
        """Return all items whose status is ``"done"``."""
        return [item for item in self._items.values() if item.status == "done"]

    def get_done_since(self, since: datetime) -> list[TodoItem]:
        """Return items completed at or after *since*.

        Only considers items with a non-None ``done_at`` timestamp.
        """
        return [
            item
            for item in self._items.values()
            if item.status == "done" and item.done_at is not None and item.done_at >= since
        ]

    def remove_completed(self) -> int:
        """Remove all completed items from the store.

        Returns the number of items removed.
        """
        done_ids = [iid for iid, item in self._items.items() if item.status == "done"]
        for iid in done_ids:
            del self._items[iid]
        if done_ids:
            logger.debug("Removed %d completed items from store", len(done_ids))
        return len(done_ids)

    def get_by_file(self, source_file: str) -> list[TodoItem]:
        """Return all items originating from *source_file*.

        Args:
            source_file: Path relative to ``notes_dir``
                (e.g. ``"2024/06/2024-06-10-meeting.md"``).
        """
        return [item for item in self._items.values() if item.source_file == source_file]

    def get_open_by_file(self, source_file: str) -> list[TodoItem]:
        """Return open items originating from *source_file*."""
        return [
            item
            for item in self._items.values()
            if item.source_file == source_file and item.status == "open"
        ]

    @property
    def count(self) -> int:
        """Total number of items in the store."""
        return len(self._items)

    @property
    def open_count(self) -> int:
        """Number of open items."""
        return sum(1 for item in self._items.values() if item.status == "open")

    def __len__(self) -> int:
        return self.count

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._items
