"""Pydantic data models for application configuration.

Config resolution order:
    CLI flags → environment variables → config.yaml → built-in defaults
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# AI configuration
# ---------------------------------------------------------------------------


class AIModelsConfig(BaseModel):
    """Model names for different AI tasks."""

    extraction: str = "gpt-5-mini"
    generation: str = "gpt-5.2"


class AIConfig(BaseModel):
    """AI provider settings."""

    provider: str = "openai"
    models: AIModelsConfig = AIModelsConfig()
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


# ---------------------------------------------------------------------------
# Extractor configuration
# ---------------------------------------------------------------------------


class ExtractorConfig(BaseModel):
    """Settings for the TODO Extractor agent."""

    watch: bool = True
    scan_glob: str = "**/*.md"
    implicit_detection: bool = True


# ---------------------------------------------------------------------------
# Manager configuration
# ---------------------------------------------------------------------------


class ManagerSchedulesConfig(BaseModel):
    """Schedule settings for plan generation."""

    morning: str = "06:00"
    afternoon: str = "12:00"
    weekly_review_day: str = "friday"
    weekly_review_time: str = "15:00"
    weekly_plan_day: str = "sunday"
    weekly_plan_time: str = "18:00"


class ManagerConfig(BaseModel):
    """Settings for the TODO Manager agent."""

    schedules: ManagerSchedulesConfig = ManagerSchedulesConfig()


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------


class LoggingConfig(BaseModel):
    """Logging settings."""

    model_config = ConfigDict(validate_default=True)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    file: Path = Path("~/.md-todos/logs/md-todos.log")

    @field_validator("file", mode="before")
    @classmethod
    def expand_log_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser()


# ---------------------------------------------------------------------------
# Top-level application configuration
# ---------------------------------------------------------------------------


class AppConfig(BaseModel):
    """Root configuration model for MD-TODOs.

    Merges values from config.yaml, environment variables, and CLI flags.
    All path fields support ``~`` expansion.
    """

    model_config = ConfigDict(validate_default=True)

    notes_dir: Path = Path("~/notes")
    plans_dir: Path = Path("~/plans")
    data_dir: Path = Path("~/.md-todos")
    store_path: Path = Path("~/.md-todos/store/todos.json")
    skills_path: Path = Path("skills/gtd.md")

    ai: AIConfig = AIConfig()
    extractor: ExtractorConfig = ExtractorConfig()
    manager: ManagerConfig = ManagerConfig()
    logging: LoggingConfig = LoggingConfig()

    @field_validator(
        "notes_dir",
        "plans_dir",
        "data_dir",
        "store_path",
        "skills_path",
        mode="before",
    )
    @classmethod
    def expand_user_paths(cls, v: str | Path) -> Path:
        return Path(v).expanduser()
