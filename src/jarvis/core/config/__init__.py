"""Configuration package.

Public API:

    from jarvis.core.config import Settings, load_settings, paths, constants
"""

from __future__ import annotations

from jarvis.core.config import constants, paths
from jarvis.core.config.settings import Settings, load_settings

__all__ = ["Settings", "constants", "load_settings", "paths"]
