"""Extractor agent — the main entry point for TODO extraction.

The agent ties together file parsing, diff/sync logic, the file watcher,
and initial full-scan into a cohesive daemon.  It can run in two modes:

- **Watch mode** (default): performs an initial full scan, then watches the
  notes directory for changes indefinitely.
- **Full scan only** (``--full``): scans all Markdown files once and exits.

Usage::

    from src.extractor.agent import ExtractorAgent

    agent = ExtractorAgent(config)
    agent.run()            # watch mode (blocking)
    agent.run_full_scan()  # one-shot scan
"""

from __future__ import annotations

from pathlib import Path

from src.ai.provider import AIProvider
from src.common.config_models import AppConfig
from src.common.logging import get_logger
from src.common.store import TodoStore
from src.common.todo_models import TodoItem
from src.extractor.diff import mark_file_deleted, sync_file_todos
from src.extractor.file_parser import parse_file
from src.extractor.watcher import NotesWatcher

logger = get_logger(__name__)


class ExtractorAgent:
    """Watches a notes directory and extracts TODOs into a shared store.

    Args:
        config: Application configuration.
        provider: Optional AI provider for implicit TODO detection.
            When *None*, only regex detection is used.
        store: Optional pre-initialised store. If *None*, one is created
            from ``config.store_path``.
    """

    def __init__(
        self,
        config: AppConfig,
        *,
        provider: AIProvider | None = None,
        store: TodoStore | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._notes_dir = config.notes_dir.expanduser().resolve()
        self._scan_glob = config.extractor.scan_glob
        self._implicit_detection = config.extractor.implicit_detection

        # Store
        self._store = store or TodoStore(config.store_path)
        self._store.load()

        # Watcher (created on demand)
        self._watcher: NotesWatcher | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def store(self) -> TodoStore:
        """The TODO store managed by this agent."""
        return self._store

    @property
    def notes_dir(self) -> Path:
        """Resolved notes directory path."""
        return self._notes_dir

    # ------------------------------------------------------------------
    # Full scan
    # ------------------------------------------------------------------

    def run_full_scan(self) -> int:
        """Scan all Markdown files in the notes directory.

        For each file matching the scan glob, parse it and sync the
        results against the store.

        Returns:
            Total number of TODO items found across all files.
        """
        if not self._notes_dir.is_dir():
            logger.error("Notes directory does not exist: %s", self._notes_dir)
            return 0

        md_files = sorted(self._notes_dir.glob(self._scan_glob))
        md_files = [f for f in md_files if f.is_file()]

        logger.info(
            "Starting full scan of %d Markdown files in %s",
            len(md_files),
            self._notes_dir,
        )

        total_added = 0
        total_updated = 0
        total_done = 0

        for file_path in md_files:
            try:
                items = self._parse(file_path)
                source_file = self._relative_path(file_path)
                added, updated, done = sync_file_todos(self._store, source_file, items)
                total_added += added
                total_updated += updated
                total_done += done
            except (OSError, ValueError, RuntimeError):
                logger.exception("Error scanning file: %s", file_path)

        self._store.save()

        total_open = self._store.open_count
        logger.info(
            "Full scan complete: +%d added, ~%d updated, -%d done. Store has %d open TODOs.",
            total_added,
            total_updated,
            total_done,
            total_open,
        )
        return total_open

    # ------------------------------------------------------------------
    # Watch mode
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the extractor in watch mode (blocking).

        1. Perform an initial full scan to bootstrap / refresh the store.
        2. Watch for file changes and process them in real time.
        3. Block until interrupted (KeyboardInterrupt / SIGINT).
        """
        logger.info("Extractor agent starting (watch mode)")

        # Initial scan
        self.run_full_scan()

        # Start the watcher
        self._watcher = NotesWatcher(
            notes_dir=self._notes_dir,
            scan_glob=self._scan_glob,
            on_file_changed=self._handle_file_changed,
            on_file_deleted=self._handle_file_deleted,
        )
        self._watcher.run_forever()

        logger.info("Extractor agent stopped")

    # ------------------------------------------------------------------
    # Event handlers (called by the watcher)
    # ------------------------------------------------------------------

    def _handle_file_changed(self, file_path: Path) -> None:
        """Called when a Markdown file is created or modified."""
        logger.debug("Processing change: %s", file_path)
        try:
            items = self._parse(file_path)
            source_file = self._relative_path(file_path)
            added, updated, done = sync_file_todos(self._store, source_file, items)
            self._store.save()
            logger.debug(
                "Synced %s: +%d, ~%d, -%d",
                source_file,
                added,
                updated,
                done,
            )
        except FileNotFoundError:
            # File may have been deleted between the event and our read
            logger.debug("File disappeared before parsing: %s", file_path)
        except (OSError, ValueError, RuntimeError):
            logger.exception("Error processing change for %s", file_path)

    def _handle_file_deleted(self, file_path: Path) -> None:
        """Called when a Markdown file is deleted."""
        logger.debug("Processing deletion: %s", file_path)
        try:
            source_file = self._relative_path(file_path)
            done_count = mark_file_deleted(self._store, source_file)
            if done_count > 0:
                self._store.save()
                logger.debug("Marked %d TODOs done for deleted %s", done_count, source_file)
        except (OSError, ValueError, RuntimeError):
            logger.exception("Error processing deletion of %s", file_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse(self, file_path: Path) -> list[TodoItem]:
        """Parse a file using both regex and (optionally) AI detection."""
        return parse_file(
            file_path,
            self._notes_dir,
            provider=self._provider,
            implicit_detection=self._implicit_detection,
        )

    def _relative_path(self, file_path: Path) -> str:
        """Compute the source_file path relative to notes_dir."""
        resolved = file_path.resolve()
        try:
            return str(resolved.relative_to(self._notes_dir))
        except ValueError:
            return str(resolved)
