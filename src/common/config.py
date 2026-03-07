"""Configuration loader for MD-TODOs.

Resolution order (highest priority first):
    1. CLI flags (applied by callers after loading)
    2. Environment variables (MD_TODOS_* prefix)
    3. config.yaml file
    4. Built-in defaults (from Pydantic model)
"""

import os
from pathlib import Path
from typing import Any

import yaml

from src.common.config_models import AppConfig

# Default config file location
DEFAULT_CONFIG_PATH = Path("~/.md-todos/config.yaml")

# Environment variable prefix
_ENV_PREFIX = "MD_TODOS_"

# Mapping of env var suffixes → nested config keys (dot-separated)
_ENV_MAP: dict[str, str] = {
    "NOTES_DIR": "notes_dir",
    "PLANS_DIR": "plans_dir",
    "DATA_DIR": "data_dir",
    "STORE_PATH": "store_path",
    "SKILLS_PATH": "skills_path",
    "AI_PROVIDER": "ai.provider",
    "AI_MODEL_EXTRACTION": "ai.models.extraction",
    "AI_MODEL_GENERATION": "ai.models.generation",
    "AI_MAX_TOKENS": "ai.max_tokens",
    "AI_TEMPERATURE": "ai.temperature",
    "EXTRACTOR_WATCH": "extractor.watch",
    "EXTRACTOR_SCAN_GLOB": "extractor.scan_glob",
    "EXTRACTOR_IMPLICIT_DETECTION": "extractor.implicit_detection",
    "LOG_LEVEL": "logging.level",
    "LOG_FILE": "logging.file",
}


def _set_nested(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Set a value in a nested dict using a dot-separated key path."""
    keys = dotted_key.split(".")
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _coerce_env_value(value: str) -> str | int | float | bool:
    """Coerce a string env value to a more specific Python type."""
    lowered = value.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Merge matching MD_TODOS_* environment variables into the config dict."""
    for suffix, dotted_key in _ENV_MAP.items():
        env_key = f"{_ENV_PREFIX}{suffix}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            _set_nested(data, dotted_key, _coerce_env_value(env_val))
    return data


def load_yaml(config_path: Path) -> dict[str, Any]:
    """Load a YAML config file and return its contents as a dict.

    Returns an empty dict if the file does not exist.
    """
    config_path = config_path.expanduser()
    if not config_path.is_file():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw if isinstance(raw, dict) else {}


def load_config(
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load and resolve the application configuration.

    Args:
        config_path: Path to the YAML config file. Defaults to
            ``~/.md-todos/config.yaml``.
        cli_overrides: Optional dict of dotted-key overrides applied last
            (highest priority). Example: ``{"notes_dir": "/tmp/notes"}``.

    Returns:
        A fully resolved ``AppConfig`` instance.
    """
    path = (config_path or DEFAULT_CONFIG_PATH).expanduser()

    # Layer 1: Load YAML (or empty dict if missing)
    data = load_yaml(path)

    # Layer 2: Apply environment variable overrides
    data = _apply_env_overrides(data)

    # Layer 3: Apply CLI overrides (flat top-level keys only for now)
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None:
                _set_nested(data, key, value)

    # Layer 4: Pydantic fills in defaults for anything still missing
    return AppConfig(**data)
