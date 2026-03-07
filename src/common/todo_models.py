"""Pydantic model for a TODO item extracted from Markdown notes."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TodoItem(BaseModel):
    """A single TODO / action item extracted from a Markdown file.

    Schema mirrors Section 2.3 of the proposed solution.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier (UUID v4).",
    )
    text: str = Field(
        description="The TODO text / action item description.",
    )
    source_file: str = Field(
        description="Source file path relative to notes_dir.",
    )
    source_line: int = Field(
        ge=1,
        description="1-based line number in the source file.",
    )
    surrounding_context: str = Field(
        default="",
        description="Two lines above and below the TODO for context.",
    )
    detection_method: Literal["checkbox", "keyword", "ai_implicit"] = Field(
        description="How the TODO was detected.",
    )
    status: Literal["open", "done"] = Field(
        default="open",
        description="Current status of the TODO.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the TODO was first detected (UTC).",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the TODO was last updated (UTC).",
    )
    done_at: datetime | None = Field(
        default=None,
        description="When the TODO was marked done (UTC), or None.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="AI-assigned tags (e.g. 'personal', 'health').",
    )
    raw_checkbox_state: bool | None = Field(
        default=None,
        description="Tracks the original Markdown checkbox state. None if not a checkbox TODO.",
    )
