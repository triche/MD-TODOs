"""Tests for the ExtractorAgent — full scan, watch mode, and integration."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.common.config_models import AppConfig, ExtractorConfig
from src.extractor.agent import ExtractorAgent


def _write_md(target_dir: Path, name: str, content: str) -> Path:
    p = target_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestFullScan:
    @pytest.fixture
    def notes_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "notes"
        d.mkdir()
        return d

    @pytest.fixture
    def store_path(self, tmp_path: Path) -> Path:
        return tmp_path / "store" / "todos.json"

    @pytest.fixture
    def config(self, tmp_path: Path, notes_dir: Path, store_path: Path) -> AppConfig:
        return AppConfig(
            notes_dir=notes_dir,
            plans_dir=tmp_path / "plans",
            data_dir=tmp_path,
            store_path=store_path,
            extractor=ExtractorConfig(watch=True, scan_glob="**/*.md", implicit_detection=False),
        )

    def test_scan_empty_directory(self, config: AppConfig) -> None:
        agent = ExtractorAgent(config)
        total = agent.run_full_scan()
        assert total == 0
        assert agent.store.count == 0

    def test_scan_single_file(self, config: AppConfig, notes_dir: Path) -> None:
        _write_md(notes_dir, "test.md", "- [ ] Buy milk\nTODO: Fix bug\n")
        agent = ExtractorAgent(config)
        total = agent.run_full_scan()
        assert total == 2
        assert agent.store.open_count == 2

    def test_scan_multiple_files(self, config: AppConfig, notes_dir: Path) -> None:
        _write_md(notes_dir, "a.md", "- [ ] Task A\n")
        _write_md(notes_dir, "b.md", "- [ ] Task B\nTODO: Task C\n")
        agent = ExtractorAgent(config)
        total = agent.run_full_scan()
        assert total == 3

    def test_scan_nested_files(self, config: AppConfig, notes_dir: Path) -> None:
        _write_md(notes_dir, "2024/06/meeting.md", "- [ ] Follow up\n")
        agent = ExtractorAgent(config)
        total = agent.run_full_scan()
        assert total == 1
        items = agent.store.get_by_file("2024/06/meeting.md")
        assert len(items) == 1

    def test_scan_checked_items_are_done(self, config: AppConfig, notes_dir: Path) -> None:
        _write_md(notes_dir, "test.md", "- [x] Done task\n- [ ] Open task\n")
        agent = ExtractorAgent(config)
        agent.run_full_scan()
        assert agent.store.open_count == 1
        done = agent.store.get_done()
        assert len(done) == 1
        assert done[0].text == "Done task"

    def test_rescan_updates_store(self, config: AppConfig, notes_dir: Path) -> None:
        f = _write_md(notes_dir, "test.md", "- [ ] Task 1\n")
        agent = ExtractorAgent(config)
        agent.run_full_scan()
        assert agent.store.open_count == 1

        # Modify file: remove old, add new
        f.write_text("- [ ] Task 2\n", encoding="utf-8")
        agent.run_full_scan()
        open_items = agent.store.get_open()
        assert len(open_items) == 1
        assert open_items[0].text == "Task 2"

    def test_scan_nonexistent_dir(self, config: AppConfig) -> None:
        bad_config = config.model_copy(update={"notes_dir": Path("/nonexistent")})
        agent = ExtractorAgent(bad_config)
        total = agent.run_full_scan()
        assert total == 0

    def test_scan_ignores_non_md(self, config: AppConfig, notes_dir: Path) -> None:
        _write_md(notes_dir, "readme.txt", "- [ ] Not a markdown file\n")
        _write_md(notes_dir, "real.md", "- [ ] Real task\n")
        agent = ExtractorAgent(config)
        total = agent.run_full_scan()
        assert total == 1

    def test_scan_preserves_store(self, config: AppConfig, notes_dir: Path) -> None:
        """Full scan saves to disk and can be reloaded."""
        _write_md(notes_dir, "test.md", "- [ ] Persistent task\n")
        agent = ExtractorAgent(config)
        agent.run_full_scan()

        # Create a new agent (reloads from disk)
        agent2 = ExtractorAgent(config)
        assert agent2.store.count == 1
        assert agent2.store.get_open()[0].text == "Persistent task"


class TestFullScanWithAI:
    @pytest.fixture
    def notes_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "notes"
        d.mkdir()
        return d

    @pytest.fixture
    def store_path(self, tmp_path: Path) -> Path:
        return tmp_path / "store" / "todos.json"

    @pytest.fixture
    def config(self, tmp_path: Path, notes_dir: Path, store_path: Path) -> AppConfig:
        return AppConfig(
            notes_dir=notes_dir,
            plans_dir=tmp_path / "plans",
            data_dir=tmp_path,
            store_path=store_path,
            extractor=ExtractorConfig(watch=True, scan_glob="**/*.md", implicit_detection=False),
        )

    @pytest.fixture
    def config_with_ai(self, config: AppConfig) -> AppConfig:
        return config.model_copy(update={"extractor": ExtractorConfig(implicit_detection=True)})

    @pytest.fixture
    def mock_provider(self) -> AsyncMock:
        provider = AsyncMock()
        provider.classify = AsyncMock(return_value="not_action_item")
        return provider

    def test_ai_implicit_detection(
        self, config_with_ai: AppConfig, notes_dir: Path, mock_provider: AsyncMock
    ) -> None:
        content = (
            "# Meeting Notes\n\n"
            "We discussed the upcoming deadline.\n\n"
            "I should send the report to the team by Friday.\n\n"
            "- [ ] Prepare slides\n"
        )
        _write_md(notes_dir, "meeting.md", content)

        mock_provider.classify = AsyncMock(
            side_effect=lambda text, cats: "action_item" if "report" in text else "not_action_item"
        )

        agent = ExtractorAgent(config_with_ai, provider=mock_provider)
        agent.run_full_scan()

        # 1 checkbox + 1 AI implicit
        assert agent.store.open_count == 2
        ai_items = [i for i in agent.store.get_open() if i.detection_method == "ai_implicit"]
        assert len(ai_items) == 1


class TestIntegrationCreateModifyDelete:
    """Integration test: create, modify, and delete files, verify store state."""

    @pytest.fixture
    def notes_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "notes"
        d.mkdir()
        return d

    @pytest.fixture
    def store_path(self, tmp_path: Path) -> Path:
        return tmp_path / "store" / "todos.json"

    @pytest.fixture
    def config(self, tmp_path: Path, notes_dir: Path, store_path: Path) -> AppConfig:
        return AppConfig(
            notes_dir=notes_dir,
            plans_dir=tmp_path / "plans",
            data_dir=tmp_path,
            store_path=store_path,
            extractor=ExtractorConfig(watch=True, scan_glob="**/*.md", implicit_detection=False),
        )

    def test_create_modify_delete_cycle(self, config: AppConfig, notes_dir: Path) -> None:
        agent = ExtractorAgent(config)

        # Step 1: Create a file and scan
        f = _write_md(notes_dir, "cycle.md", "- [ ] Task A\n- [ ] Task B\n")
        agent.run_full_scan()
        assert agent.store.open_count == 2

        # Step 2: Modify — check one task, add a new one
        f.write_text("- [x] Task A\n- [ ] Task B\n- [ ] Task C\n", encoding="utf-8")
        agent.run_full_scan()
        assert agent.store.open_count == 2  # B and C
        done = agent.store.get_done()
        assert any(i.text == "Task A" for i in done)

        # Step 3: Delete the file
        f.unlink()
        # Manually trigger deletion handling (in watch mode, the watcher does this)
        from src.extractor.diff import mark_file_deleted

        mark_file_deleted(agent.store, "cycle.md")
        agent.store.save()
        assert agent.store.open_count == 0

    def test_multiple_files_independent(self, config: AppConfig, notes_dir: Path) -> None:
        _write_md(notes_dir, "a.md", "- [ ] Task from A\n")
        _write_md(notes_dir, "b.md", "- [ ] Task from B\n")

        agent = ExtractorAgent(config)
        agent.run_full_scan()

        # Modify only a.md
        _write_md(notes_dir, "a.md", "- [x] Task from A\n- [ ] New from A\n")
        agent.run_full_scan()

        a_items = agent.store.get_by_file("a.md")
        b_items = agent.store.get_by_file("b.md")

        a_open = [i for i in a_items if i.status == "open"]
        assert len(a_open) == 1
        assert a_open[0].text == "New from A"

        assert len(b_items) == 1
        assert b_items[0].status == "open"


class TestWatchMode:
    """Test that the agent's watch mode detects file changes in real time."""

    @pytest.fixture
    def notes_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "notes"
        d.mkdir()
        return d

    @pytest.fixture
    def store_path(self, tmp_path: Path) -> Path:
        return tmp_path / "store" / "todos.json"

    @pytest.fixture
    def config(self, tmp_path: Path, notes_dir: Path, store_path: Path) -> AppConfig:
        return AppConfig(
            notes_dir=notes_dir,
            plans_dir=tmp_path / "plans",
            data_dir=tmp_path,
            store_path=store_path,
            extractor=ExtractorConfig(watch=True, scan_glob="**/*.md", implicit_detection=False),
        )

    def test_watcher_detects_new_file(self, config: AppConfig, notes_dir: Path) -> None:
        agent = ExtractorAgent(config)
        agent.run_full_scan()

        # Set up watcher manually (don't block with run_forever)
        from src.extractor.watcher import NotesWatcher

        watcher = NotesWatcher(
            notes_dir=agent.notes_dir,
            scan_glob=config.extractor.scan_glob,
            on_file_changed=agent._handle_file_changed,  # pylint: disable=protected-access
            on_file_deleted=agent._handle_file_deleted,  # pylint: disable=protected-access
        )
        watcher.start()
        try:
            _write_md(notes_dir, "watched.md", "- [ ] Watched task\n")
            time.sleep(2)

            assert agent.store.open_count >= 1
            items = agent.store.get_by_file("watched.md")
            assert len(items) >= 1
        finally:
            watcher.stop()
