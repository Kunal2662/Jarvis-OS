"""File Platform domain — Milestone 11 Task Group C."""

from __future__ import annotations

from jarvis.domain.files.models import (
    ATTACHMENT_TARGETS,
    DEFAULT_MIME_TYPE,
    INDEX_STATUSES,
    MAX_EXTRACT_BYTES,
    TEXT_EXTRACTABLE_EXTENSIONS,
    FilePathError,
    extension_of,
    extract_text,
    guess_mime_type,
    safe_join,
    validate_name,
)

__all__ = [
    "ATTACHMENT_TARGETS",
    "DEFAULT_MIME_TYPE",
    "INDEX_STATUSES",
    "MAX_EXTRACT_BYTES",
    "TEXT_EXTRACTABLE_EXTENSIONS",
    "FilePathError",
    "extension_of",
    "extract_text",
    "guess_mime_type",
    "safe_join",
    "validate_name",
]
