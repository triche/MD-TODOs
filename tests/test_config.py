"""Unit tests for configuration loading."""

from pathlib import Path

import pytest
import yaml

from src.common.config import load_config, load_yaml

# ── Helpers ───────────────────────────────────────────────────


def _write_yaml(path: Path, data: dict) -> Path:
    """Write a dict as YAML to *path* and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


# ── Tests: load_yaml ─────────────────────────────────────────


class TestLoadYaml:
    """Tests for the raw YAML loader."""

    def test_returns_empty_dict_when_file_missing(self, tmp_path: Path) -> None:
        result = load_yaml(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        cfg_file = _write_yaml(tmp_path / "config.yaml", {"notes_dir": "/tmp/notes"})
        result = load_yaml(cfg_file)
        assert result == {"notes_dir": "/tmp/notes"}

    def test_returns_empty_dict_for_empty_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("")
        result = load_yaml(cfg_file)
        assert result == {}

    def test_returns_empty_dict_for_non_dict_yaml(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("- item1\n- item2\n")
        result = load_yaml(cfg_file)
        assert result == {}


# ── Tests: load_config with defaults ─────────────────────────


class TestLoadConfigDefaults:
    """Loading config with no file and no env vars produces sane defaults."""

    def test_default_config_has_expected_paths(self, tmp_path: Path) -> None:
        config = load_config(config_path=tmp_path / "does-not-exist.yaml")
        assert config.notes_dir == Path("~/notes").expanduser()
        assert config.plans_dir == Path("~/plans").expanduser()
        assert config.data_dir == Path("~/.md-todos").expanduser()

    def test_default_ai_settings(self, tmp_path: Path) -> None:
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.ai.provider == "openai"
        assert config.ai.models.extraction == "gpt-5-mini"
        assert config.ai.models.generation == "gpt-5.2"
        assert config.ai.max_tokens == 4096
        assert config.ai.temperature == 0.3

    def test_default_extractor_settings(self, tmp_path: Path) -> None:
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.extractor.watch is True
        assert config.extractor.scan_glob == "**/*.md"
        assert config.extractor.implicit_detection is True

    def test_default_logging(self, tmp_path: Path) -> None:
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.logging.level == "INFO"
        assert config.logging.file == Path("~/.md-todos/logs/md-todos.log").expanduser()


# ── Tests: load_config from YAML file ────────────────────────


class TestLoadConfigFromFile:
    """Loading config from an actual YAML file."""

    def test_yaml_overrides_defaults(self, tmp_path: Path) -> None:
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {
                "notes_dir": str(tmp_path / "my-notes"),
                "plans_dir": str(tmp_path / "my-plans"),
                "ai": {"provider": "anthropic", "max_tokens": 2048},
            },
        )
        config = load_config(config_path=cfg_file)
        assert config.notes_dir == tmp_path / "my-notes"
        assert config.plans_dir == tmp_path / "my-plans"
        assert config.ai.provider == "anthropic"
        assert config.ai.max_tokens == 2048
        # Defaults still apply for unset fields
        assert config.ai.temperature == 0.3
        assert config.extractor.watch is True

    def test_nested_yaml_settings(self, tmp_path: Path) -> None:
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {
                "manager": {
                    "schedules": {
                        "morning": "07:30",
                        "weekly_review_day": "thursday",
                    },
                },
                "logging": {"level": "DEBUG"},
            },
        )
        config = load_config(config_path=cfg_file)
        assert config.manager.schedules.morning == "07:30"
        assert config.manager.schedules.weekly_review_day == "thursday"
        # Defaults for unset schedule fields
        assert config.manager.schedules.afternoon == "12:00"
        assert config.logging.level == "DEBUG"


# ── Tests: environment variable overrides ─────────────────────


class TestLoadConfigEnvOverrides:
    """Environment variables override YAML and defaults."""

    def test_env_overrides_notes_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_notes = str(tmp_path / "env-notes")
        monkeypatch.setenv("MD_TODOS_NOTES_DIR", env_notes)
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.notes_dir == Path(env_notes)

    def test_env_overrides_ai_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MD_TODOS_AI_PROVIDER", "azure")
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.ai.provider == "azure"

    def test_env_overrides_log_level(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MD_TODOS_LOG_LEVEL", "DEBUG")
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.logging.level == "DEBUG"

    def test_env_bool_coercion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MD_TODOS_EXTRACTOR_WATCH", "false")
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.extractor.watch is False

    def test_env_int_coercion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MD_TODOS_AI_MAX_TOKENS", "8192")
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.ai.max_tokens == 8192

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env vars take precedence over values in the YAML file."""
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {"ai": {"provider": "openai"}},
        )
        monkeypatch.setenv("MD_TODOS_AI_PROVIDER", "env-provider")
        config = load_config(config_path=cfg_file)
        assert config.ai.provider == "env-provider"


# ── Tests: CLI overrides ─────────────────────────────────────


class TestLoadConfigCLIOverrides:
    """CLI overrides have the highest priority."""

    def test_cli_overrides_env_and_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {"notes_dir": str(tmp_path / "yaml-notes")},
        )
        monkeypatch.setenv("MD_TODOS_NOTES_DIR", str(tmp_path / "env-notes"))
        cli_notes = str(tmp_path / "cli-notes")
        config = load_config(config_path=cfg_file, cli_overrides={"notes_dir": cli_notes})
        assert config.notes_dir == Path(cli_notes)

    def test_cli_nested_override(self, tmp_path: Path) -> None:
        config = load_config(
            config_path=tmp_path / "missing.yaml",
            cli_overrides={"ai.provider": "cli-provider"},
        )
        assert config.ai.provider == "cli-provider"


# ── Tests: path expansion ────────────────────────────────────


class TestPathExpansion:
    """Tilde paths are expanded to absolute paths."""

    def test_tilde_expansion(self, tmp_path: Path) -> None:
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {"notes_dir": "~/my-notes"},
        )
        config = load_config(config_path=cfg_file)
        assert config.notes_dir == Path("~/my-notes").expanduser()
        assert config.notes_dir.is_absolute()

    def test_default_paths_are_expanded(self, tmp_path: Path) -> None:
        config = load_config(config_path=tmp_path / "missing.yaml")
        assert config.data_dir.is_absolute()
        assert config.store_path.is_absolute()
        assert config.logging.file.is_absolute()


# ── Tests: TodoItem model ────────────────────────────────────


class TestTodoItemModel:
    """Verify the TodoItem Pydantic model."""

    def test_create_minimal_todo(self) -> None:
        from src.common.todo_models import TodoItem

        item = TodoItem(
            text="Buy milk",
            source_file="2024/06/notes.md",
            source_line=10,
            detection_method="checkbox",
        )
        assert item.status == "open"
        assert item.done_at is None
        assert item.tags == []
        assert item.id  # UUID is auto-generated

    def test_create_full_todo(self) -> None:
        from src.common.todo_models import TodoItem

        item = TodoItem(
            text="Schedule dentist appointment",
            source_file="2024/06/meeting.md",
            source_line=42,
            surrounding_context="context above\nTODO line\ncontext below",
            detection_method="keyword",
            status="done",
            tags=["personal", "health"],
            raw_checkbox_state=None,
        )
        assert item.status == "done"
        assert item.detection_method == "keyword"
        assert "health" in item.tags

    def test_todo_serialization_roundtrip(self) -> None:
        from src.common.todo_models import TodoItem

        item = TodoItem(
            text="Test roundtrip",
            source_file="test.md",
            source_line=1,
            detection_method="ai_implicit",
        )
        data = item.model_dump(mode="json")
        restored = TodoItem.model_validate(data)
        assert restored.text == item.text
        assert restored.id == item.id
        assert restored.created_at == item.created_at
