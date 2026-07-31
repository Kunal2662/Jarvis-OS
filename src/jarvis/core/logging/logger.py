"""Logging bootstrap built on top of *loguru* + *structlog*.

Design
------
* One global :mod:`loguru` logger — no per-module ``logging.getLogger`` calls.
* Console sink is human-friendly in dev, JSON in production.
* Rotating file sink writes to ``<data_dir>/logs/jarvis.log``.
* ``get_logger(name)`` returns a bound logger with a ``logger=<name>`` field.
* The stdlib :mod:`logging` module is intercepted so that libraries which use
  it (uvicorn, chromadb, sqlalchemy …) end up in the same pipeline.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from loguru import logger as _loguru_logger

from jarvis.core.config import paths
from jarvis.core.logging.formatters import CONSOLE_FORMAT, FILE_FORMAT

if TYPE_CHECKING:  # avoid circular import at runtime
    from jarvis.core.config.settings import Settings


_configured: bool = False


# ---------------------------------------------------------------------------
# Stdlib → loguru interception
# ---------------------------------------------------------------------------
class _InterceptHandler(logging.Handler):
    """Route stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        _loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _json_sink(message: Any) -> None:
    """Loguru sink that serialises records as one JSON object per line."""
    record = message.record
    payload = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["extra"].get("logger", record["name"]),
        "message": record["message"],
        "function": record["function"],
        "line": record["line"],
        "module": record["module"],
        "process": record["process"].id,
        "thread": record["thread"].id,
    }
    if record["exception"] is not None:
        payload["exception"] = str(record["exception"])
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def configure_logging(settings: Settings) -> None:
    """Configure the global loguru logger from :class:`Settings`.

    Idempotent — calling this more than once is safe.
    """
    global _configured
    if _configured:
        return

    _loguru_logger.remove()

    level = settings.log.level
    if settings.log.json:
        _loguru_logger.add(
            _json_sink,
            level=level,
            backtrace=False,
            diagnose=False,
            enqueue=True,
        )
    else:
        _loguru_logger.add(
            sys.stderr,
            level=level,
            format=CONSOLE_FORMAT,
            colorize=True,
            backtrace=settings.debug,
            diagnose=settings.debug,
            enqueue=True,
        )

    if settings.log.file_enabled:
        log_dir = paths.log_dir(settings.resolved_data_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        _loguru_logger.add(
            log_dir / "jarvis.log",
            level=level,
            format=FILE_FORMAT,
            rotation=settings.log.file_rotation,
            retention=settings.log.file_retention,
            encoding="utf-8",
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

    # Route the stdlib into loguru.
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "chromadb", "httpx"):
        logging.getLogger(noisy).handlers = [_InterceptHandler()]
        logging.getLogger(noisy).propagate = False

    _configured = True
    _loguru_logger.bind(logger="jarvis.core.logging").info(
        "Logging configured (level={}, json={}, file={}).",
        level,
        settings.log.json,
        settings.log.file_enabled,
    )


def get_logger(name: str):
    """Return a loguru logger bound with ``logger=<name>``."""
    return _loguru_logger.bind(logger=name)
