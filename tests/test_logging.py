"""Unit tests for the logging setup module."""

import logging
from pathlib import Path

from src.common.logging import get_logger, setup_logging


class TestSetupLogging:
    """Tests for setup_logging()."""

    def test_stream_handler_attached(self) -> None:
        # Reset root logger
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(level="WARNING")

        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
        assert root.level == logging.WARNING

        # Cleanup
        root.handlers.clear()

    def test_file_handler_created(self, tmp_path: Path) -> None:
        root = logging.getLogger()
        root.handlers.clear()

        log_file = tmp_path / "logs" / "test.log"
        setup_logging(level="DEBUG", log_file=log_file)

        assert log_file.parent.exists()
        # Should have both stream and file handler
        handler_types = {type(h).__name__ for h in root.handlers}
        assert "StreamHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

        # Write a record and verify it appears in the file
        logger = logging.getLogger("test_write")
        logger.debug("test message")
        # Flush handlers
        for h in root.handlers:
            h.flush()
        assert log_file.exists()
        content = log_file.read_text()
        assert "test message" in content

        # Cleanup
        root.handlers.clear()

    def test_no_file_handler_when_none(self) -> None:
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(level="INFO", log_file=None)

        handler_types = {type(h).__name__ for h in root.handlers}
        assert "RotatingFileHandler" not in handler_types

        # Cleanup
        root.handlers.clear()


class TestGetLogger:
    """Tests for get_logger()."""

    def test_namespaced_logger(self) -> None:
        logger = get_logger("extractor")
        assert logger.name == "md_todos.extractor"

    def test_different_names_produce_different_loggers(self) -> None:
        a = get_logger("manager")
        b = get_logger("store")
        assert a is not b
        assert a.name != b.name
