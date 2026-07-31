"""Structured logging package.

Public API::

    from jarvis.core.logging import configure_logging, get_logger
"""

from __future__ import annotations

from jarvis.core.logging.logger import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]
