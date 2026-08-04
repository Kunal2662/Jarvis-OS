"""Filesystem path resolution.

Encapsulates *all* on-disk paths the app uses at runtime. Every other module
must ask this module for a path — never build one by hand.

Two axes:

* **Base data dir** — either from ``JARVIS_DATA_DIR`` or the OS-appropriate
  per-user application-data directory.
* **Repository root** — resolved from ``__file__`` and used to locate
  bundled resources (`resources/themes`, `resources/icons`, ...).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

from jarvis.core.config import constants


# ---------------------------------------------------------------------------
# Repository root  (works both from a checkout and from a PyInstaller bundle)
# ---------------------------------------------------------------------------
def _resolve_repo_root() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    # src/jarvis/core/config/paths.py  →  repo root is 4 parents up
    return Path(__file__).resolve().parents[4]


REPO_ROOT: Final[Path] = _resolve_repo_root()
RESOURCES_DIR: Final[Path] = REPO_ROOT / "resources"
THEMES_DIR: Final[Path] = RESOURCES_DIR / "themes"
ICONS_DIR: Final[Path] = RESOURCES_DIR / "icons"
FONTS_DIR: Final[Path] = RESOURCES_DIR / "fonts"
ASSETS_DIR: Final[Path] = RESOURCES_DIR / "assets"


# ---------------------------------------------------------------------------
# Runtime data dir
# ---------------------------------------------------------------------------
def default_data_dir() -> Path:
    """OS-appropriate per-user data dir.

    * Windows :  ``%LOCALAPPDATA%\\JarvisOS``
    * macOS   :  ``~/Library/Application Support/JarvisOS``
    * Linux   :  ``$XDG_DATA_HOME/jarvis-os``  or  ``~/.local/share/jarvis-os``
    """
    env_override = os.environ.get(f"{constants.ENV_PREFIX}DATA_DIR")
    if env_override:
        return Path(env_override).expanduser().resolve()

    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / constants.APP_ORG
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / constants.APP_ORG
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / constants.APP_ID


def resolve_data_dir(configured: str | Path | None) -> Path:
    """Resolve the configured data dir (from Settings) to an absolute path."""
    if configured is None or str(configured).strip() == "":
        return default_data_dir()
    return Path(configured).expanduser().resolve()


def ensure_runtime_dirs(data_dir: Path) -> None:
    """Create the standard runtime subdirectories if they do not exist yet."""
    for sub in (
        constants.DB_SUBDIR,
        constants.VECTOR_SUBDIR,
        constants.LOG_SUBDIR,
        constants.CACHE_SUBDIR,
        constants.RECIPES_SUBDIR,
        constants.TRASH_SUBDIR,
        constants.CONFIG_SUBDIR,
        constants.PLUGINS_SUBDIR,
    ):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Convenience getters (bound at import time to REPO_ROOT-relative locations)
# ---------------------------------------------------------------------------
def db_path(data_dir: Path) -> Path:
    return data_dir / constants.DB_SUBDIR / constants.DEFAULT_DB_FILE


def agent_checkpoint_db_path(data_dir: Path) -> Path:
    """SQLite file backing the LangGraph checkpointer (Milestone 5-Agents).

    Deliberately a separate file from :func:`db_path` — LangGraph's
    ``AsyncSqliteSaver`` opens its own ``aiosqlite`` connection outside
    SQLAlchemy's pool, and sharing one file risks lock contention between
    the two independent writers.
    """
    return data_dir / constants.DB_SUBDIR / constants.DEFAULT_AGENT_CHECKPOINT_DB_FILE


def vector_dir(data_dir: Path) -> Path:
    return data_dir / constants.VECTOR_SUBDIR


def log_dir(data_dir: Path) -> Path:
    return data_dir / constants.LOG_SUBDIR


def cache_dir(data_dir: Path) -> Path:
    return data_dir / constants.CACHE_SUBDIR


def recipes_dir(data_dir: Path) -> Path:
    """User-writable JSON automation recipes (Milestone 4)."""
    return data_dir / constants.RECIPES_SUBDIR


def automation_trash_dir(data_dir: Path) -> Path:
    """Soft-delete staging area so ``delete_folder``/``rename``/``move`` are undoable."""
    return data_dir / constants.TRASH_SUBDIR


def config_dir(data_dir: Path) -> Path:
    """Milestone 5 -- JSON config stores (API Center, restore points, ...)."""
    return data_dir / constants.CONFIG_SUBDIR


def plugins_dir(data_dir: Path) -> Path:
    """Milestone 9 Task Group D -- installed plugin directories, one
    subfolder per plugin (``<plugins_dir>/<plugin_id>/manifest.json``)."""
    return data_dir / constants.PLUGINS_SUBDIR
