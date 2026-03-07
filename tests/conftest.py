"""Shared test fixtures for MD-TODOs."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory mimicking ~/.md-todos/."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    return tmp_path


@pytest.fixture
def tmp_notes_dir(tmp_path: Path) -> Path:
    """Create a temporary notes directory."""
    notes = tmp_path / "notes"
    notes.mkdir()
    return notes


@pytest.fixture
def tmp_plans_dir(tmp_path: Path) -> Path:
    """Create a temporary plans directory."""
    plans = tmp_path / "plans"
    plans.mkdir()
    return plans
