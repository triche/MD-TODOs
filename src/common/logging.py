"""Structured logging setup for MD-TODOs.

Configures a root logger with both a file handler (rotating) and a stream
handler.  Call ``setup_logging()`` once at application startup.

Privacy note: TODO content must only be logged at DEBUG level, never at
INFO or above, because user notes may contain sensitive information.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    log_file: Path | None = None,
) -> None:
    """Configure the root logger for the application.

    Args:
        level: Logging level.
        log_file: Optional path to a log file.  Parent directories are
            created automatically.  If *None*, only the stream handler
            is attached.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level))

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    # ── Stream handler (stderr) ────────────────────────────────
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # ── File handler (optional, rotating) ──────────────────────
    if log_file is not None:
        log_file = log_file.expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger namespaced under ``md_todos``."""
    return logging.getLogger(f"md_todos.{name}")
