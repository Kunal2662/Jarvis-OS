"""Runtime settings service.

Milestone 1: reads from :class:`Settings` and lets the UI write a *runtime*
override into memory + persist selected keys back to the ``.env`` file
next to the app so the next launch picks them up.

We do **not** try to hot-swap providers here — the user restarts the app
(or clicks "Apply & Restart") after changing critical values like the
default LLM provider. That's simpler and safer for a single-user desktop
app than in-flight DI re-wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from jarvis.core.exceptions import ServiceError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings

_logger = get_logger("jarvis.services.settings")


# Keys the UI is allowed to persist to `.env`. Anything outside this
# whitelist is refused so the user cannot brick the app from the Settings
# dialog.
_WRITABLE_KEYS: frozenset[str] = frozenset(
    {
        "JARVIS_LLM_DEFAULT_PROVIDER",
        "JARVIS_LLM_FALLBACK_PROVIDER",
        "JARVIS_OPENAI_ENABLED",
        "JARVIS_OPENAI_API_KEY",
        "JARVIS_OPENAI_BASE_URL",
        "JARVIS_OPENAI_CHAT_MODEL",
        "JARVIS_OPENAI_ORG",
        "JARVIS_OLLAMA_ENABLED",
        "JARVIS_OLLAMA_BASE_URL",
        "JARVIS_OLLAMA_MODEL",
        "JARVIS_GEMINI_ENABLED",
        "JARVIS_GEMINI_API_KEY",
        "JARVIS_GEMINI_BASE_URL",
        "JARVIS_GEMINI_CHAT_MODEL",
        "JARVIS_GEMINI_EMBEDDING_MODEL",
        "JARVIS_UI_THEME",
        "JARVIS_UI_ACCENT",
        "JARVIS_UI_START_MINIMIZED",
        "JARVIS_UI_STREAMING_MODE",
        "JARVIS_UI_SYSTEM_PROMPT",
        "JARVIS_LOG_LEVEL",
        "JARVIS_LOG_JSON",
        "JARVIS_LOG_FILE_ENABLED",
        # --- Voice / STT / TTS (Milestone 2) ---
        "JARVIS_STT_ENABLED",
        "JARVIS_STT_BACKEND",
        "JARVIS_STT_MODEL",
        "JARVIS_STT_LANGUAGE",
        "JARVIS_TTS_ENABLED",
        "JARVIS_TTS_BACKEND",
        "JARVIS_TTS_VOICE",
        "JARVIS_TTS_MODEL",
        "JARVIS_TTS_PLAYBACK_SPEED",
        "JARVIS_TTS_PITCH",
        "JARVIS_TTS_VOLUME",
        "JARVIS_TTS_STREAMING",
        "JARVIS_TTS_SPEAK_REPLIES",
        "JARVIS_PIPER_ENABLED",
        "JARVIS_PIPER_VOICE",
        "JARVIS_PIPER_MODEL_PATH",
        "JARVIS_PIPER_EXECUTABLE",
        "JARVIS_KOKORO_ENABLED",
        "JARVIS_KOKORO_VOICE",
        "JARVIS_KOKORO_MODEL_PATH",
        "JARVIS_KOKORO_LANGUAGE",
        "JARVIS_EDGE_TTS_ENABLED",
        "JARVIS_EDGE_TTS_VOICE",
        "JARVIS_EDGE_TTS_RATE",
        "JARVIS_EDGE_TTS_PITCH_HZ",
        "JARVIS_ELEVENLABS_ENABLED",
        "JARVIS_ELEVENLABS_API_KEY",
        "JARVIS_ELEVENLABS_VOICE_ID",
        "JARVIS_ELEVENLABS_MODEL",
        "JARVIS_VOICE_MODE",
        "JARVIS_VOICE_PUSH_TO_TALK_HOTKEY",
        "JARVIS_VOICE_TOGGLE_HOTKEY",
        "JARVIS_VOICE_INPUT_DEVICE",
        "JARVIS_VOICE_OUTPUT_DEVICE",
        "JARVIS_VOICE_CONTINUOUS_CONVERSATION",
        "JARVIS_VOICE_INTERRUPT_ENABLED",
        "JARVIS_VOICE_INTERRUPT_VAD_THRESHOLD",
        "JARVIS_WAKE_ENABLED",
        "JARVIS_WAKE_ENGINE",
        "JARVIS_WAKE_KEYWORDS",
        "JARVIS_WAKE_SENSITIVITY",
        "JARVIS_WAKE_MODEL_PATH",
        "JARVIS_WAKE_ACCESS_KEY",
        "JARVIS_HOTKEY_TOGGLE_WINDOW",
        "JARVIS_HOTKEY_ENABLED",
        # --- Memory (Milestone 3) ---
        "JARVIS_MEMORY_ENABLED",
        "JARVIS_MEMORY_MAX_MEMORIES",
        "JARVIS_MEMORY_RETENTION_DAYS",
        "JARVIS_MEMORY_AUTO_SUMMARIZE",
        "JARVIS_MEMORY_RECALL_TOP_K",
        "JARVIS_MEMORY_RECALL_MIN_SCORE",
        # --- Developer Mode / Update Center / Voice Announcements (Milestone 5) ---
        "JARVIS_DEV_MODE_PASSWORD_HASH",
        "JARVIS_DEV_MODE_SESSION_TIMEOUT_MINUTES",
        "JARVIS_UPDATE_CHANNEL",
        "JARVIS_UPDATE_AUTO_CHECK",
        "JARVIS_UPDATE_CHECK_INTERVAL_HOURS",
        "JARVIS_UPDATE_CREATE_RESTORE_POINT",
        "JARVIS_VOICE_ANNOUNCE_ENABLED",
        "JARVIS_VOICE_ANNOUNCE_STYLE",
        "JARVIS_VOICE_ANNOUNCE_VOLUME",
        "JARVIS_VOICE_ANNOUNCE_SPEED",
        "JARVIS_VOICE_ANNOUNCE_LANGUAGE",
        # --- Agent Runtime (Milestone 5-Agents) ---
        "JARVIS_AGENT_MAX_STEPS",
        "JARVIS_AGENT_TIMEOUT_SECONDS",
        "JARVIS_AGENT_CHECKPOINT_ENABLED",
        # --- Vision & Multimodal (Milestone 6) ---
        "JARVIS_VISION_ENABLED",
        "JARVIS_OCR_ENABLED",
    }
)


class SettingsService:
    def __init__(self, settings: Settings, env_file: Path | None = None) -> None:
        self._settings = settings
        self._env_file = env_file or Path.cwd() / ".env"

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """The **full** settings tree, secrets included where the model
        does not wrap them.

        In-process callers only -- the PySide6 Configuration Manager view
        runs inside the same trust boundary as the ``.env`` file it is
        displaying. Anything that leaves the process must use
        :meth:`public_snapshot` instead.
        """
        return self._settings.model_dump(mode="json")

    def public_snapshot(self) -> dict[str, Any]:
        """The settings tree with every secret redacted -- the only form
        that may cross a process boundary (M8 Phase 2).

        Two serializers rather than one, the same split
        ``Credential.to_storage_dict`` / ``to_public_dict`` already uses
        in ``core/mcp/auth/credentials.py``, and for the same reason: a
        single method that callers must remember to sanitise is a method
        somebody will forget to sanitise.

        **Why this is not redundant with ``SecretStr``.** Pydantic
        redacts a ``SecretStr`` on dump, which covers ``openai.api_key``
        and friends. It does *not* cover a secret living inside a plain
        container -- ``integrations.clients`` (M11 Task Group E) is a
        ``dict[str, dict[str, str]]`` whose ``client_secret`` entries
        dump verbatim. Redacting by *key name* here catches that case and
        every future one shaped like it, which typing alone would not.
        """
        # `_redact` is genuinely polymorphic -- it returns a str for a
        # secret leaf, a dict for a mapping, a list for a sequence -- so
        # its return type is `Any`. The cast is safe because a dict input
        # always produces a dict: the only branch that could return
        # something else needs a secret-looking `key`, and the top-level
        # call passes none.
        return cast("dict[str, Any]", _redact(self._settings.model_dump(mode="json")))

    def get(self, dotted_key: str) -> Any:
        node: Any = self._settings
        for part in dotted_key.split("."):
            node = getattr(node, part)
        return node

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def writable_keys(self) -> list[str]:
        return sorted(_WRITABLE_KEYS)

    async def set_env(self, key: str, value: str) -> None:
        """Persist ``KEY=value`` into the ``.env`` file (creating it if needed).

        Raises :class:`ServiceError` for keys outside the writable whitelist.
        """
        if key not in _WRITABLE_KEYS:
            raise ServiceError(f"Setting {key!r} is not user-writable.")
        self._upsert_env(key, value)
        _logger.info("Persisted {} to {}", key, self._env_file)

    def _upsert_env(self, key: str, value: str) -> None:
        line = f"{key}={value}"
        if not self._env_file.exists():
            self._env_file.write_text(line + "\n", encoding="utf-8")
            return
        lines = self._env_file.read_text(encoding="utf-8").splitlines()
        replaced = False
        for i, raw in enumerate(lines):
            stripped = raw.lstrip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines[i] = line
                replaced = True
                break
        if not replaced:
            lines.append(line)
        self._env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


#: Substrings that mark a settings key as secret. Matched
#: case-insensitively against the *key*, not the value, because a value
#: heuristic ("looks like a token") both misses real secrets and redacts
#: innocent strings. Deliberately broad: a redacted non-secret is a
#: cosmetic problem, a leaked secret is not.
_SECRET_KEY_MARKERS: tuple[str, ...] = (
    "secret",
    "password",
    "api_key",
    "apikey",
    "token",
    "credential",
    "private_key",
)

#: What a redacted value is replaced with. Matches what pydantic's own
#: ``SecretStr`` renders, so a consumer cannot tell which mechanism did
#: the redacting and does not need to.
REDACTED = "**********"


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def _redact(value: Any, *, key: str = "") -> Any:
    """Recursively replace secret-looking leaves.

    A secret key whose value is a container redacts the whole container
    rather than descending into it -- ``{"credentials": {...}}`` should
    not leak because the nesting hid it from a leaf-only check.
    """
    if key and _is_secret_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: _redact(v, key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
