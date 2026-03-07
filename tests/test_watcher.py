"""Unit tests for the file watcher."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.extractor.watcher import NotesWatcher, _MarkdownEventHandler


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    d = tmp_path / "notes"
    d.mkdir()
    return d


@pytest.fixture
def on_changed() -> MagicMock:
    return MagicMock()


@pytest.fixture
def on_deleted() -> MagicMock:
    return MagicMock()


class TestMarkdownEventHandler:
    """Test the watchdog event handler in isolation."""

    def test_matches_md_files(self, notes_dir: Path) -> None:
        handler = _MarkdownEventHandler(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=MagicMock(),
            on_file_deleted=MagicMock(),
        )
        assert handler._matches_glob(notes_dir / "test.md") is True
        assert handler._matches_glob(notes_dir / "sub" / "test.md") is True
        assert handler._matches_glob(notes_dir / "test.txt") is False
        assert handler._matches_glob(notes_dir / "test.py") is False

    def test_ignores_non_matching_files(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        handler = _MarkdownEventHandler(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        handler._handle_change(str(notes_dir / "test.txt"))
        on_changed.assert_not_called()

    def test_dispatches_matching_files(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        handler = _MarkdownEventHandler(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        handler._handle_change(str(notes_dir / "test.md"))
        on_changed.assert_called_once_with(notes_dir / "test.md")

    def test_debounce(self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock) -> None:
        handler = _MarkdownEventHandler(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        path = str(notes_dir / "test.md")
        handler._handle_change(path)
        handler._handle_change(path)  # should be debounced
        assert on_changed.call_count == 1

    def test_delete_dispatches(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        handler = _MarkdownEventHandler(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        handler._handle_delete(str(notes_dir / "removed.md"))
        on_deleted.assert_called_once_with(notes_dir / "removed.md")


class TestNotesWatcher:
    """Integration-level tests for the watcher."""

    def test_start_stop(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        watcher = NotesWatcher(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        assert not watcher.running
        watcher.start()
        assert watcher.running
        watcher.stop()
        assert not watcher.running

    def test_start_nonexistent_dir(
        self, tmp_path: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        watcher = NotesWatcher(
            notes_dir=tmp_path / "nonexistent",
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        with pytest.raises(FileNotFoundError):
            watcher.start()

    def test_detects_file_creation(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        """Create a file while watching and verify the callback fires."""
        watcher = NotesWatcher(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        watcher.start()
        try:
            # Create a file
            test_file = notes_dir / "new.md"
            test_file.write_text("- [ ] New task\n", encoding="utf-8")

            # Give FSEvents time to fire
            time.sleep(1.5)

            assert on_changed.call_count >= 1
            # The callback should have received the path
            called_paths = [call.args[0] for call in on_changed.call_args_list]
            assert any(p.name == "new.md" for p in called_paths)
        finally:
            watcher.stop()

    def test_detects_file_modification(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        """Modify an existing file and verify the callback fires."""
        test_file = notes_dir / "existing.md"
        test_file.write_text("# Notes\n", encoding="utf-8")

        watcher = NotesWatcher(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        watcher.start()
        try:
            time.sleep(0.5)  # let watcher settle

            test_file.write_text("# Notes\n- [ ] Updated task\n", encoding="utf-8")
            time.sleep(1.5)

            assert on_changed.call_count >= 1
        finally:
            watcher.stop()

    def test_detects_file_deletion(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        """Delete a file and verify the callback fires."""
        test_file = notes_dir / "to_delete.md"
        test_file.write_text("- [ ] Will be removed\n", encoding="utf-8")

        watcher = NotesWatcher(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        watcher.start()
        try:
            time.sleep(0.5)  # let watcher settle

            test_file.unlink()
            time.sleep(1.5)

            assert on_deleted.call_count >= 1
        finally:
            watcher.stop()

    def test_ignores_non_md_files(
        self, notes_dir: Path, on_changed: MagicMock, on_deleted: MagicMock
    ) -> None:
        """Non-Markdown files should not trigger callbacks."""
        watcher = NotesWatcher(
            notes_dir=notes_dir,
            scan_glob="**/*.md",
            on_file_changed=on_changed,
            on_file_deleted=on_deleted,
        )
        watcher.start()
        try:
            (notes_dir / "readme.txt").write_text("text file\n", encoding="utf-8")
            time.sleep(1.5)

            # on_changed should NOT have been called for the .txt file
            # (it may have been called for directory events, so check the paths)
            for call in on_changed.call_args_list:
                called_path = call.args[0]
                assert called_path.suffix != ".txt"
        finally:
            watcher.stop()
