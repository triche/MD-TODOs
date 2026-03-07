"""Tests for CLI commands using click.testing.CliRunner."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Create a minimal config.yaml in a temp directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "store").mkdir()
    (data_dir / "logs").mkdir()

    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()

    config_path = data_dir / "config.yaml"
    config_path.write_text(
        f"notes_dir: {notes_dir}\n"
        f"plans_dir: {plans_dir}\n"
        f"data_dir: {data_dir}\n"
        f"store_path: {data_dir / 'store' / 'todos.json'}\n"
        f"skills_path: skills/gtd.md\n"
        "logging:\n"
        "  level: WARNING\n"
        f"  file: {data_dir / 'logs' / 'md-todos.log'}\n"
        "extractor:\n"
        "  implicit_detection: false\n",
        encoding="utf-8",
    )
    return config_path


# ── CLI group ────────────────────────────────────────────────


class TestCLIGroup:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "MD-TODOs" in result.output
        assert "extract" in result.output
        assert "plan" in result.output
        assert "status" in result.output
        assert "install" in result.output
        assert "uninstall" in result.output

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


# ── extract ──────────────────────────────────────────────────


class TestExtractCommand:
    def test_extract_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["extract", "--help"])
        assert result.exit_code == 0
        assert "--full" in result.output

    def test_extract_full_scan(self, runner: CliRunner, config_file: Path, tmp_path: Path) -> None:
        notes_dir = tmp_path / "notes"
        (notes_dir / "test.md").write_text("- [ ] Buy milk\n", encoding="utf-8")

        result = runner.invoke(cli, ["--config", str(config_file), "extract", "--full"])
        assert result.exit_code == 0
        assert "Full scan complete" in result.output
        assert "1 open TODOs" in result.output

    def test_extract_full_scan_empty(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["--config", str(config_file), "extract", "--full"])
        assert result.exit_code == 0
        assert "0 open TODOs" in result.output

    def test_extract_full_scan_multiple(
        self, runner: CliRunner, config_file: Path, tmp_path: Path
    ) -> None:
        notes_dir = tmp_path / "notes"
        (notes_dir / "a.md").write_text("- [ ] Task A\n", encoding="utf-8")
        (notes_dir / "b.md").write_text("TODO: Task B\n", encoding="utf-8")

        result = runner.invoke(cli, ["--config", str(config_file), "extract", "--full"])
        assert result.exit_code == 0
        assert "2 open TODOs" in result.output

    def test_extract_watch_mode_starts(self, runner: CliRunner, config_file: Path) -> None:
        """Watch mode should print the start message then block.

        We mock the watcher to prevent actual blocking.
        """
        with patch("src.extractor.agent.NotesWatcher") as mock_watcher_cls:
            mock_watcher = MagicMock()
            mock_watcher.run_forever.side_effect = KeyboardInterrupt
            mock_watcher_cls.return_value = mock_watcher

            result = runner.invoke(cli, ["--config", str(config_file), "extract"])
            assert result.exit_code == 0
            assert "watch mode" in result.output.lower()


# ── plan ─────────────────────────────────────────────────────


class TestPlanCommand:
    def test_plan_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        assert "--type" in result.output
        assert "morning" in result.output

    def test_plan_requires_type(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["--config", str(config_file), "plan"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "--type" in result.output

    def test_plan_invalid_type(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["--config", str(config_file), "plan", "--type", "invalid"])
        assert result.exit_code != 0

    def test_plan_generates_file(
        self, runner: CliRunner, config_file: Path, tmp_path: Path
    ) -> None:
        """Plan command should call generate_plan_sync and report the output path."""
        plan_file = tmp_path / "plans" / "2026" / "03" / "2026-03-07-morning.md"

        with (
            patch("src.ai.factory.create_provider") as mock_factory,
            patch("src.manager.agent.ManagerAgent.generate_plan_sync") as mock_gen,
        ):
            mock_provider = MagicMock()
            mock_factory.return_value = mock_provider
            mock_gen.return_value = plan_file

            result = runner.invoke(cli, ["--config", str(config_file), "plan", "--type", "morning"])
            assert result.exit_code == 0
            assert "Plan written to" in result.output
            mock_gen.assert_called_once_with("morning")

    def test_plan_no_api_key_error(self, runner: CliRunner, config_file: Path) -> None:
        """If no API key is available, plan should show an error."""
        from src.ai.provider import AIProviderAuthError

        with patch("src.ai.factory.create_provider") as mock_factory:
            mock_factory.side_effect = AIProviderAuthError("No API key found")

            result = runner.invoke(cli, ["--config", str(config_file), "plan", "--type", "morning"])
            assert result.exit_code != 0
            assert "No API key" in result.output


# ── status ───────────────────────────────────────────────────


class TestStatusCommand:
    def test_status_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0

    def test_status_empty_store(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["--config", str(config_file), "status"])
        assert result.exit_code == 0
        assert "Open:" in result.output
        assert "Done:" in result.output
        assert "Total:" in result.output

    def test_status_shows_paths(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["--config", str(config_file), "status"])
        assert result.exit_code == 0
        assert "Notes dir:" in result.output
        assert "Plans dir:" in result.output
        assert "Config:" in result.output

    def test_status_shows_agents(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["--config", str(config_file), "status"])
        assert result.exit_code == 0
        assert "Agents:" in result.output

    def test_status_with_populated_store(
        self, runner: CliRunner, config_file: Path, tmp_path: Path
    ) -> None:
        """Populate the store with TODOs and verify status reports correctly."""
        notes_dir = tmp_path / "notes"
        (notes_dir / "test.md").write_text(
            "- [ ] Task 1\n- [x] Done task\nTODO: Task 2\n",
            encoding="utf-8",
        )

        # First, extract to populate the store
        result = runner.invoke(cli, ["--config", str(config_file), "extract", "--full"])
        assert result.exit_code == 0

        # Then check status
        result = runner.invoke(cli, ["--config", str(config_file), "status"])
        assert result.exit_code == 0
        # Should show open and done counts
        assert "Open:" in result.output
        assert "Total:" in result.output


# ── install ──────────────────────────────────────────────────


class TestInstallCommand:
    def test_install_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["install", "--help"])
        assert result.exit_code == 0

    def test_install_creates_data_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Install should create the data directory if missing."""
        config_path = tmp_path / "new-data" / "config.yaml"

        with patch("src.cli.main._setup_api_key"):
            result = runner.invoke(cli, ["--config", str(config_path), "install"])
            assert result.exit_code == 0
            assert (tmp_path / "new-data").is_dir()
            assert "Created" in result.output or "Data directory exists" in result.output

    def test_install_copies_config_template(self, runner: CliRunner, tmp_path: Path) -> None:
        """Install should copy the config template."""
        config_path = tmp_path / "new-data" / "config.yaml"

        with patch("src.cli.main._setup_api_key"):
            result = runner.invoke(cli, ["--config", str(config_path), "install"])
            assert result.exit_code == 0
            # Config was created from template (if template exists in the repo)
            assert "config" in result.output.lower()

    def test_install_existing_data_dir(self, runner: CliRunner, config_file: Path) -> None:
        """Install should note when data dir already exists."""
        with patch("src.cli.main._setup_api_key"):
            result = runner.invoke(cli, ["--config", str(config_file), "install"])
            assert result.exit_code == 0
            assert "exists" in result.output.lower()


# ── uninstall ────────────────────────────────────────────────


class TestUninstallCommand:
    def test_uninstall_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["uninstall", "--help"])
        assert result.exit_code == 0
        assert "--all" in result.output

    def test_uninstall_no_agents(self, runner: CliRunner, config_file: Path) -> None:
        """Uninstall without agents should report they're not installed."""
        result = runner.invoke(cli, ["--config", str(config_file), "uninstall"])
        assert result.exit_code == 0
        assert "not installed" in result.output

    def test_uninstall_all_removes_data(self, runner: CliRunner, config_file: Path) -> None:
        """Uninstall --all should remove data dir (after confirmation)."""
        data_dir = config_file.parent

        with patch("src.ai.keychain.delete_api_key", return_value=False):
            result = runner.invoke(
                cli,
                ["--config", str(config_file), "uninstall", "--all"],
                input="y\n",
            )
            assert result.exit_code == 0
            assert not data_dir.is_dir()

    def test_uninstall_all_decline_data_removal(self, runner: CliRunner, config_file: Path) -> None:
        """Declining confirmation should keep data dir."""
        data_dir = config_file.parent

        with patch("src.ai.keychain.delete_api_key", return_value=False):
            result = runner.invoke(
                cli,
                ["--config", str(config_file), "uninstall", "--all"],
                input="n\n",
            )
            assert result.exit_code == 0
            assert data_dir.is_dir()


# ── config override ──────────────────────────────────────────


class TestConfigOverride:
    def test_custom_config_path(self, runner: CliRunner, config_file: Path) -> None:
        """The --config flag should work with status command."""
        result = runner.invoke(cli, ["--config", str(config_file), "status"])
        assert result.exit_code == 0

    def test_missing_config_falls_back_to_defaults(self, runner: CliRunner) -> None:
        """When config file is missing, Pydantic defaults should apply."""
        result = runner.invoke(
            cli,
            ["--config", "/nonexistent/config.yaml", "status"],
        )
        # Should still succeed — missing config gives empty dict, Pydantic fills defaults
        assert result.exit_code == 0
