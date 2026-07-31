"""Shared, framework-free type aliases and small value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, TypeAlias

# --- Primitive type aliases -------------------------------------------------
JSON: TypeAlias = dict[str, Any]
Role: TypeAlias = Literal["system", "user", "assistant", "tool"]


class Environment(str, Enum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProviderName(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    GEMINI = "gemini"


class STTBackend(str, Enum):
    WHISPER_LOCAL = "whisper_local"
    OPENAI_WHISPER = "openai_whisper"
    DEEPGRAM = "deepgram"  # reserved — Milestone 2.1


class TTSBackend(str, Enum):
    PIPER = "piper"  # primary offline TTS
    KOKORO = "kokoro"  # optional offline TTS
    EDGE_TTS = "edge_tts"  # free, online, streaming
    ELEVENLABS = "elevenlabs"  # premium, online, streaming
    OPENAI = "openai"  # online


class WakeWordEngine(str, Enum):
    NONE = "none"
    PORCUPINE = "porcupine"
    OPENWAKEWORD = "openwakeword"


class VoiceState(str, Enum):
    """States of the voice conversation state machine.

    Transitions (nominal path)::

        IDLE -> LISTENING -> THINKING -> SPEAKING -> IDLE (or LISTENING
        again when continuous-conversation mode is on)

    ``INTERRUPTED`` is entered from ``SPEAKING`` the instant the user
    starts talking again, and immediately falls through to ``LISTENING``.
    ``OFFLINE`` and ``ERROR`` can be entered from anywhere.
    """

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    OFFLINE = "offline"
    ERROR = "error"


class VoiceMode(str, Enum):
    """How JARVIS listens for input."""

    PUSH_TO_TALK = "push_to_talk"  # mic active only while a hotkey is held
    TOGGLE = "toggle"  # hotkey toggles listening on/off
    ALWAYS_ON = "always_on"  # continuously listens — reserved for wake word


class ThemeName(str, Enum):
    DARK = "dark"
    LIGHT = "light"
    JARVIS = "jarvis"


class StreamingMode(str, Enum):
    """How assistant tokens should appear in the UI."""

    TYPEWRITER = "typewriter"  # token-by-token append
    CHUNK = "chunk"  # chunk-by-chunk with typing indicator


class MemoryType(str, Enum):
    """Classification of a stored memory — Milestone 3.

    Every :class:`~jarvis.infrastructure.database.models.Memory` row is
    tagged with exactly one of these. The value is free-form enough to be
    stored as a plain string column (no DB-level enum), so adding a new
    type later never requires a migration.
    """

    CONVERSATION = "conversation"  # a turn or summary from a chat
    LONG_TERM = "long_term"  # durable fact promoted from conversation
    PREFERENCE = "preference"  # explicit user preference ("call me Sam")
    PROJECT = "project"  # project-scoped knowledge
    TASK = "task"  # task/to-do related memory
    FILE = "file"  # memory about a file the user referenced
    AI_CONTEXT = "ai_context"  # AI-authored context/scratchpad note


# --- Small value objects ----------------------------------------------------
@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    name: str
    enabled: bool
    healthy: bool
    detail: str = ""
