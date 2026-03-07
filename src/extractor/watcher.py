"""File system watcher using ``watchdog`` (FSEvents on macOS).

Monitors the notes directory for Markdown file changes and triggers
the extractor's parse-and-sync pipeline for each event.
"""

from __future__ import annotations

import fnmatch
import time
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from src.common.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

# Debounce window in seconds — group rapid successive events for the same file.
_DEBOUNCE_SECONDS = 0.5


class _MarkdownEventHandler(FileSystemEventHandler):
    """Watchdog handler that dispatches Markdown file events.

    Only files matching the configured glob pattern (default ``**/*.md``)
    are processed.  Events are debounced so that rapid successive saves
    don't trigger multiple parse cycles for the same file.

    Args:
        notes_dir: Absolute path to the notes root.
        scan_glob: Glob pattern for Markdown files (e.g. ``**/*.md``).
        on_file_changed: Callback for created or modified files.
            Receives the absolute ``Path`` to the changed file.
        on_file_deleted: Callback for deleted files.
            Receives the absolute ``Path`` to the deleted file.
    """

    def __init__(
        self,
        notes_dir: Path,
        scan_glob: str,
        on_file_changed: Callable[[Path], None],
        on_file_deleted: Callable[[Path], None],
    ) -> None:
        super().__init__()
        self._notes_dir = notes_dir.resolve()
        self._scan_glob = scan_glob
        self._on_file_changed = on_file_changed
        self._on_file_deleted = on_file_deleted
        self._last_event: dict[str, float] = {}

    def _matches_glob(self, path: Path) -> bool:
        """Check if *path* matches the configured scan glob."""
        try:
            relative = path.resolve().relative_to(self._notes_dir)
        except ValueError:
            return False
        # fnmatch doesn't support ** the way glob does, so we need to
        # handle the common **/*.ext pattern by checking the suffix.
        pattern = self._scan_glob
        if pattern.startswith("**/"):
            # Strip the **/ prefix and match the remaining pattern against
            # just the filename (for simple patterns like **/*.md).
            suffix_pattern = pattern[3:]
            return fnmatch.fnmatch(relative.name, suffix_pattern)
        return fnmatch.fnmatch(str(relative), pattern)

    def _is_debounced(self, path: str) -> bool:
        """Return True if we should skip this event (too soon after the last)."""
        now = time.monotonic()
        last = self._last_event.get(path, 0.0)
        if now - last < _DEBOUNCE_SECONDS:
            return True
        self._last_event[path] = now
        return False

    def on_created(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileCreatedEvent):
            self._handle_change(str(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileModifiedEvent):
            self._handle_change(str(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileDeletedEvent):
            self._handle_delete(str(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileMovedEvent):
            # Treat old path as deleted, new path as created
            self._handle_delete(str(event.src_path))
            self._handle_change(str(event.dest_path))

    def _handle_change(self, src_path: str) -> None:
        """Process a create or modify event."""
        path = Path(src_path)
        if not self._matches_glob(path):
            return
        if self._is_debounced(src_path):
            logger.debug("Debounced event for %s", src_path)
            return
        logger.debug("File changed: %s", src_path)
        try:
            self._on_file_changed(path)
        except (OSError, ValueError, RuntimeError):
            logger.exception("Error processing file change: %s", src_path)

    def _handle_delete(self, src_path: str) -> None:
        """Process a delete event."""
        path = Path(src_path)
        if not self._matches_glob(path):
            return
        logger.debug("File deleted: %s", src_path)
        try:
            self._on_file_deleted(path)
        except (OSError, ValueError, RuntimeError):
            logger.exception("Error processing file deletion: %s", src_path)


class NotesWatcher:
    """Watches the notes directory for Markdown file changes.

    Usage::

        watcher = NotesWatcher(
            notes_dir=Path("~/notes"),
            scan_glob="**/*.md",
            on_file_changed=handle_change,
            on_file_deleted=handle_delete,
        )
        watcher.start()
        # ... run until interrupted ...
        watcher.stop()

    Args:
        notes_dir: Absolute path to the notes root directory.
        scan_glob: Glob pattern for Markdown files.
        on_file_changed: Callback invoked when a matching file is created
            or modified.
        on_file_deleted: Callback invoked when a matching file is deleted.
    """

    def __init__(
        self,
        notes_dir: Path,
        scan_glob: str,
        on_file_changed: Callable[[Path], None],
        on_file_deleted: Callable[[Path], None],
    ) -> None:
        self._notes_dir = notes_dir.resolve()
        self._handler = _MarkdownEventHandler(
            notes_dir=self._notes_dir,
            scan_glob=scan_glob,
            on_file_changed=on_file_changed,
            on_file_deleted=on_file_deleted,
        )
        self._observer = Observer()
        self._running = False

    @property
    def running(self) -> bool:
        """Whether the watcher is currently active."""
        return self._running

    def start(self) -> None:
        """Start watching the notes directory (non-blocking).

        The observer thread runs in the background. Call :meth:`stop` or
        :meth:`run_forever` to manage its lifecycle.
        """
        if self._running:
            logger.warning("Watcher already running")
            return

        if not self._notes_dir.is_dir():
            msg = f"Notes directory does not exist: {self._notes_dir}"
            raise FileNotFoundError(msg)

        self._observer.schedule(self._handler, str(self._notes_dir), recursive=True)
        self._observer.start()
        self._running = True
        logger.info("Started watching %s", self._notes_dir)

    def stop(self) -> None:
        """Stop the watcher and wait for the observer thread to finish."""
        if not self._running:
            return
        self._observer.stop()
        self._observer.join()
        self._running = False
        logger.info("Stopped watching %s", self._notes_dir)

    def run_forever(self, poll_interval: float = 1.0) -> None:
        """Block the current thread until interrupted (``KeyboardInterrupt``).

        Calls :meth:`start` if not already running, then polls in a loop.

        Args:
            poll_interval: Seconds between alive-checks.
        """
        if not self._running:
            self.start()

        try:
            while self._observer.is_alive():
                self._observer.join(timeout=poll_interval)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received — stopping watcher")
        finally:
            self.stop()
