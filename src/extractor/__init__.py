"""Extractor agent — watches notes and extracts action items."""

from src.extractor.agent import ExtractorAgent
from src.extractor.ai_detector import detect_implicit_todos, detect_implicit_todos_sync
from src.extractor.diff import mark_file_deleted, sync_file_todos
from src.extractor.file_parser import parse_file, parse_file_async
from src.extractor.regex_detector import detect_todos, detect_todos_in_file
from src.extractor.watcher import NotesWatcher

__all__ = [
    "ExtractorAgent",
    "NotesWatcher",
    "detect_implicit_todos",
    "detect_implicit_todos_sync",
    "detect_todos",
    "detect_todos_in_file",
    "mark_file_deleted",
    "parse_file",
    "parse_file_async",
    "sync_file_todos",
]
