"""Tests for CLI commands using click.testing.CliRunner."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.main import _render_plist, _resolve_plan_type, cli


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

    def test_uninstall_no_agents(
        self, runner: CliRunner, config_file: Path
    ) -> None:
        """Uninstall without agents should complete successfully."""
        # Mock subprocess so we don't interact with real launchctl
        with patch("src.cli.main.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = runner.invoke(cli, ["--config", str(config_file), "uninstall"])
            assert result.exit_code == 0
            # Should either report "not installed" or successfully unload
            assert "Done" in result.output or "not installed" in result.output

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


# ── plan-dispatch ────────────────────────────────────────────


class TestPlanDispatch:
    def test_plan_dispatch_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["plan-dispatch", "--help"])
        assert result.exit_code == 0
        assert "Auto-detect" in result.output

    def test_plan_dispatch_no_match(self, runner: CliRunner, config_file: Path) -> None:
        """If current time doesn't match any schedule, should exit gracefully."""
        # 3 AM on a Tuesday — no plan type matches
        with patch("src.cli.main._resolve_plan_type", return_value=None):
            result = runner.invoke(cli, ["--config", str(config_file), "plan-dispatch"])
            assert result.exit_code == 0
            assert "No plan type matches" in result.output

    def test_plan_dispatch_morning(self, runner: CliRunner, config_file: Path) -> None:
        """Dispatch should generate morning plan when matched."""
        plan_file = Path("/tmp/test-plan.md")

        with (
            patch("src.cli.main._resolve_plan_type", return_value="morning"),
            patch("src.ai.factory.create_provider") as mock_factory,
            patch("src.manager.agent.ManagerAgent.generate_plan_sync") as mock_gen,
        ):
            mock_factory.return_value = MagicMock()
            mock_gen.return_value = plan_file

            result = runner.invoke(cli, ["--config", str(config_file), "plan-dispatch"])
            assert result.exit_code == 0
            assert "Plan written to" in result.output
            mock_gen.assert_called_once_with("morning")


# ── _resolve_plan_type ───────────────────────────────────────


class TestResolvePlanType:
    def test_morning_monday_0600(self) -> None:
        now = datetime(2026, 3, 9, 6, 0)  # Monday
        assert _resolve_plan_type(now) == "morning"

    def test_morning_friday_0615(self) -> None:
        now = datetime(2026, 3, 13, 6, 15)  # Friday
        assert _resolve_plan_type(now) == "morning"

    def test_afternoon_wednesday_1200(self) -> None:
        now = datetime(2026, 3, 11, 12, 0)  # Wednesday
        assert _resolve_plan_type(now) == "afternoon"

    def test_afternoon_within_tolerance(self) -> None:
        now = datetime(2026, 3, 10, 11, 45)  # Tuesday 11:45
        assert _resolve_plan_type(now) == "afternoon"

    def test_weekly_review_friday_1500(self) -> None:
        now = datetime(2026, 3, 13, 15, 0)  # Friday 15:00
        assert _resolve_plan_type(now) == "weekly-review"

    def test_weekly_plan_sunday_1800(self) -> None:
        now = datetime(2026, 3, 8, 18, 0)  # Sunday 18:00
        assert _resolve_plan_type(now) == "weekly-plan"

    def test_no_match_saturday_0800(self) -> None:
        now = datetime(2026, 3, 14, 8, 0)  # Saturday
        assert _resolve_plan_type(now) is None

    def test_no_match_tuesday_0300(self) -> None:
        now = datetime(2026, 3, 10, 3, 0)  # Tuesday 3 AM
        assert _resolve_plan_type(now) is None

    def test_no_match_outside_tolerance(self) -> None:
        now = datetime(2026, 3, 9, 7, 0)  # Monday 7:00 — 60 min from 6:00
        assert _resolve_plan_type(now) is None

    def test_weekly_review_takes_priority_over_afternoon(self) -> None:
        """Friday 15:00 should be weekly-review, not afternoon."""
        now = datetime(2026, 3, 13, 15, 0)  # Friday 15:00
        assert _resolve_plan_type(now) == "weekly-review"


# ── _render_plist ────────────────────────────────────────────


class TestRenderPlist:
    def test_render_substitutes_placeholders(self, tmp_path: Path) -> None:
        template = tmp_path / "template.plist"
        template.write_text(
            "<string>{{PYTHON_PATH}}</string>\n"
            "<string>{{REPO_DIR}}</string>\n"
            "<string>{{CONFIG_PATH}}</string>\n"
            "<string>{{LOG_DIR}}</string>\n",
            encoding="utf-8",
        )
        output = tmp_path / "output.plist"

        _render_plist(
            template,
            output,
            {
                "{{PYTHON_PATH}}": "/usr/bin/python3",
                "{{REPO_DIR}}": "/home/user/MD-TODOs",
                "{{CONFIG_PATH}}": "/home/user/.md-todos/config.yaml",
                "{{LOG_DIR}}": "/home/user/.md-todos/logs",
            },
        )

        content = output.read_text(encoding="utf-8")
        assert "/usr/bin/python3" in content
        assert "/home/user/MD-TODOs" in content
        assert "/home/user/.md-todos/config.yaml" in content
        assert "/home/user/.md-todos/logs" in content
        assert "{{" not in content

    def test_render_preserves_unmatched_text(self, tmp_path: Path) -> None:
        template = tmp_path / "template.plist"
        template.write_text(
            "<key>Label</key>\n<string>com.md-todos.extractor</string>\n",
            encoding="utf-8",
        )
        output = tmp_path / "output.plist"
        _render_plist(template, output, {})

        content = output.read_text(encoding="utf-8")
        assert "com.md-todos.extractor" in content


# ── install with launchd ─────────────────────────────────────


class TestInstallLaunchd:
    def test_install_renders_plists(self, runner: CliRunner, tmp_path: Path) -> None:
        """Install should render plist templates."""
        config_path = tmp_path / "new-data" / "config.yaml"

        with (
            patch("src.cli.main._setup_api_key"),
            patch("src.cli.main._install_launchd_agents") as mock_launchd,
            patch("src.extractor.agent.ExtractorAgent") as mock_agent_cls,
        ):
            mock_agent = MagicMock()
            mock_agent.run_full_scan.return_value = 0
            mock_agent_cls.return_value = mock_agent

            result = runner.invoke(cli, ["--config", str(config_path), "install"])
            assert result.exit_code == 0
            mock_launchd.assert_called_once()

    def test_install_runs_initial_scan(self, runner: CliRunner, config_file: Path) -> None:
        """Install should run an initial full scan."""
        with (
            patch("src.cli.main._setup_api_key"),
            patch("src.cli.main._install_launchd_agents"),
        ):
            result = runner.invoke(cli, ["--config", str(config_file), "install"])
            assert result.exit_code == 0
            assert "Initial scan complete" in result.output


# ── plist templates ──────────────────────────────────────────


class TestPlistTemplates:
    """Validate that plist template files are well-formed and contain expected placeholders."""

    def _repo_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def test_extractor_plist_template_exists(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.extractor.plist"
        assert template.is_file()

    def test_manager_plist_template_exists(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.manager.plist"
        assert template.is_file()

    def test_extractor_plist_has_placeholders(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.extractor.plist"
        content = template.read_text(encoding="utf-8")
        assert "{{PYTHON_PATH}}" in content
        assert "{{REPO_DIR}}" in content
        assert "{{CONFIG_PATH}}" in content
        assert "{{LOG_DIR}}" in content

    def test_manager_plist_has_placeholders(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.manager.plist"
        content = template.read_text(encoding="utf-8")
        assert "{{PYTHON_PATH}}" in content
        assert "{{REPO_DIR}}" in content
        assert "{{CONFIG_PATH}}" in content
        assert "{{LOG_DIR}}" in content

    def test_extractor_plist_has_keep_alive(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.extractor.plist"
        content = template.read_text(encoding="utf-8")
        assert "<key>KeepAlive</key>" in content
        assert "<true/>" in content

    def test_manager_plist_has_calendar_intervals(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.manager.plist"
        content = template.read_text(encoding="utf-8")
        assert "<key>StartCalendarInterval</key>" in content

    def test_manager_plist_uses_plan_dispatch(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.manager.plist"
        content = template.read_text(encoding="utf-8")
        assert "plan-dispatch" in content

    def test_extractor_plist_label(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.extractor.plist"
        content = template.read_text(encoding="utf-8")
        assert "com.md-todos.extractor" in content

    def test_manager_plist_label(self) -> None:
        template = self._repo_dir() / "templates" / "com.md-todos.manager.plist"
        content = template.read_text(encoding="utf-8")
        assert "com.md-todos.manager" in content


# ── shell scripts ────────────────────────────────────────────


class TestShellScripts:
    """Validate that shell scripts exist, are executable, and contain expected content."""

    def _repo_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def test_install_script_exists(self) -> None:
        script = self._repo_dir() / "scripts" / "install.sh"
        assert script.is_file()

    def test_install_script_executable(self) -> None:
        import os
        import stat

        script = self._repo_dir() / "scripts" / "install.sh"
        mode = os.stat(script).st_mode
        assert mode & stat.S_IXUSR

    def test_uninstall_script_exists(self) -> None:
        script = self._repo_dir() / "scripts" / "uninstall.sh"
        assert script.is_file()

    def test_uninstall_script_executable(self) -> None:
        import os
        import stat

        script = self._repo_dir() / "scripts" / "uninstall.sh"
        mode = os.stat(script).st_mode
        assert mode & stat.S_IXUSR

    def test_install_script_checks_prerequisites(self) -> None:
        script = self._repo_dir() / "scripts" / "install.sh"
        content = script.read_text(encoding="utf-8")
        assert "Python" in content
        assert "macOS" in content or "Darwin" in content

    def test_install_script_creates_venv(self) -> None:
        script = self._repo_dir() / "scripts" / "install.sh"
        content = script.read_text(encoding="utf-8")
        assert "venv" in content

    def test_install_script_renders_plists(self) -> None:
        script = self._repo_dir() / "scripts" / "install.sh"
        content = script.read_text(encoding="utf-8")
        assert "render_plist" in content
        assert "LaunchAgents" in content

    def test_install_script_loads_agents(self) -> None:
        script = self._repo_dir() / "scripts" / "install.sh"
        content = script.read_text(encoding="utf-8")
        assert "launchctl load" in content

    def test_uninstall_script_unloads_agents(self) -> None:
        script = self._repo_dir() / "scripts" / "uninstall.sh"
        content = script.read_text(encoding="utf-8")
        assert "launchctl unload" in content

    def test_uninstall_script_supports_all_flag(self) -> None:
        script = self._repo_dir() / "scripts" / "uninstall.sh"
        content = script.read_text(encoding="utf-8")
        assert "--all" in content

    def test_install_script_has_non_interactive(self) -> None:
        script = self._repo_dir() / "scripts" / "install.sh"
        content = script.read_text(encoding="utf-8")
        assert "--non-interactive" in content
