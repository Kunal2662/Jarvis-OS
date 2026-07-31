"""Log formatters shared between console and file sinks."""

from __future__ import annotations

# Pretty, colorised console format for development.
CONSOLE_FORMAT: str = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "<level>{level: <8}</level> "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
    "- <level>{message}</level>"
)

# Concise, non-coloured format for file logs — grep-friendly.
FILE_FORMAT: str = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | " "{name}:{function}:{line} - {message}"
)

# JSON keys used when JARVIS_LOG_JSON=true (production).
JSON_KEYS: tuple[str, ...] = (
    "timestamp",
    "level",
    "logger",
    "message",
    "function",
    "line",
    "module",
    "process",
    "thread",
)
