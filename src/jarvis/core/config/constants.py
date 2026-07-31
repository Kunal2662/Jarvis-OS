"""Immutable constants used across the codebase.

Anything that can change at deploy time belongs in
:class:`jarvis.core.config.settings.Settings` — this module only holds
identifiers, magic strings and hard-coded limits that never change.
"""

from __future__ import annotations

from typing import Final

# --- Identity ---------------------------------------------------------------
APP_NAME: Final[str] = "JARVIS OS"
APP_ID: Final[str] = "jarvis-os"
APP_ORG: Final[str] = "JarvisOS"
APP_DOMAIN: Final[str] = "jarvis-os.local"

# --- Env var prefix ---------------------------------------------------------
ENV_PREFIX: Final[str] = "JARVIS_"

# --- Filesystem layout (relative to the runtime data dir) -------------------
DB_SUBDIR: Final[str] = "db"
VECTOR_SUBDIR: Final[str] = "vectorstore"
LOG_SUBDIR: Final[str] = "logs"
CACHE_SUBDIR: Final[str] = "cache"
RECIPES_SUBDIR: Final[str] = "recipes"
TRASH_SUBDIR: Final[str] = "cache/automation_trash"
CONFIG_SUBDIR: Final[str] = "config"

DEFAULT_LOG_FILE: Final[str] = "jarvis.log"
DEFAULT_DB_FILE: Final[str] = "jarvis.db"
DEFAULT_AGENT_CHECKPOINT_DB_FILE: Final[str] = "agent_checkpoints.db"

# --- Hard limits (safety rails, not tunables) -------------------------------
MAX_PROMPT_TOKENS: Final[int] = 128_000
MAX_TTS_TEXT_LEN: Final[int] = 4_096
MAX_STT_AUDIO_SECONDS: Final[int] = 60 * 30  # 30 min
MAX_AGENT_STEPS_HARD_CAP: Final[int] = 200

# --- Timeouts (seconds) -----------------------------------------------------
DEFAULT_HTTP_TIMEOUT: Final[float] = 30.0
DEFAULT_STARTUP_TIMEOUT: Final[float] = 10.0
DEFAULT_SHUTDOWN_TIMEOUT: Final[float] = 5.0
