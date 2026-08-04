"""Strongly-typed application settings powered by *pydantic-settings*.

Design goals
------------
* **Single source of truth** — every tunable value lives here.
* **Fail fast** — invalid configuration raises at boot, not at first use.
* **Providers as feature flags** — every external provider has an
  ``enabled`` bool; disabling a provider must never break the app.
* **Nested & flat** — nested Pydantic models keep the code readable while
  the ``env_nested_delimiter="__"`` + ``env_prefix="JARVIS_"`` combo keeps
  the ``.env`` file flat and greppable.

.env keys use the pattern::

    JARVIS_<SECTION>_<FIELD>            → e.g. JARVIS_OPENAI_API_KEY

Sections that are single fields (log, api, db, ...) are exposed both as flat
keys (``JARVIS_LOG_LEVEL``) and as nested models (``settings.log.level``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis.core.config import paths as _paths
from jarvis.core.config.constants import ENV_PREFIX

# Nested settings models below (OpenAISettings, GeminiSettings, ...) each
# declare their own ``env_prefix`` but — unlike the root ``Settings``
# model — do *not* set ``env_file``, since pydantic-settings only applies
# the parent's ``env_file`` to the top-level model, not to nested
# sub-models built via ``default_factory``. Without this, values written
# to ``.env`` (e.g. by the Settings UI / SettingsService) would only take
# effect for root-level fields and silently be ignored for every
# provider block. Loading ``.env`` into the real process environment here
# means both root and nested models see it consistently, the same way
# they would if the shell had exported it.
_dotenv_path = Path(".env")
if _dotenv_path.exists():
    load_dotenv(_dotenv_path, override=False)
from jarvis.core.exceptions import ConfigError
from jarvis.core.types import (
    Environment,
    LLMProviderName,
    StreamingMode,
    STTBackend,
    ThemeName,
    TTSBackend,
    VoiceMode,
    WakeWordEngine,
)


# ---------------------------------------------------------------------------
# Nested sections
# ---------------------------------------------------------------------------
class LoggingSettings(BaseSettings):
    level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json: bool = Field(default=False, alias="JARVIS_LOG_JSON")
    file_enabled: bool = True
    file_rotation: str = "20 MB"
    file_retention: str = "14 days"

    model_config = SettingsConfigDict(
        env_prefix=f"{ENV_PREFIX}LOG_",
        extra="ignore",
        protected_namespaces=(),
        populate_by_name=True,
    )


class ApiSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8765
    reload: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost", "http://127.0.0.1"]
    )

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}API_", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


class DatabaseSettings(BaseSettings):
    url: str = "sqlite+aiosqlite:///./data/db/jarvis.db"
    echo: bool = False

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}DB_", extra="ignore")


class VectorStoreSettings(BaseSettings):
    dir: Path = Path("./data/vectorstore")
    collection: str = "jarvis_memory"
    embedding_model: str = "text-embedding-3-small"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}VECTOR_", extra="ignore")


class MemorySettings(BaseSettings):
    """Milestone 3 — Semantic Memory tunables.

    Every value here is safe to change at runtime from the Settings ▸
    Memory page; nothing here gates DI wiring (the hook is always
    registered), so toggling ``enabled`` only changes whether
    :class:`SemanticMemoryRecallHook` actually queries the store.
    """

    enabled: bool = True
    max_memories: int = 5000  # hard cap enforced by pruning policy
    retention_days: int = 0  # 0 = keep forever (no expiration)
    auto_summarize: bool = True  # summarize conversations into long-term memory
    recall_top_k: int = 4  # memories injected per chat turn
    recall_min_score: float = 0.15  # similarity floor for recall

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}MEMORY_", extra="ignore")


class KnowledgeSettings(BaseSettings):
    """Milestone 10A — Universal Search & Knowledge Platform tunables."""

    enabled: bool = True
    default_entity_confidence: float = 0.7
    correction_confidence: float = 0.95
    reflection_batch_size: int = 20  # memories per learn_from_recent_memories() call
    search_top_k: int = 20

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}KNOWLEDGE_", extra="ignore")


class OpenAISettings(BaseSettings):
    enabled: bool = False
    api_key: SecretStr = SecretStr("")
    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    org: str = ""

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}OPENAI_", extra="ignore")


class OllamaSettings(BaseSettings):
    enabled: bool = True
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1:8b-instruct-q4_K_M"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}OLLAMA_", extra="ignore")


class GeminiSettings(BaseSettings):
    """Google AI Studio / Gemini API.

    Kept as a secondary/fallback provider by default (see
    ``llm_fallback_provider``) — "use only when necessary" per the
    person's own preference, rather than as the default chat provider.
    """

    enabled: bool = False
    api_key: SecretStr = SecretStr("")
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    chat_model: str = "gemini-2.0-flash"
    embedding_model: str = "text-embedding-004"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}GEMINI_", extra="ignore")


class STTSettings(BaseSettings):
    enabled: bool = True
    backend: STTBackend = STTBackend.WHISPER_LOCAL
    model: str = "base"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    language: str = "en"
    sample_rate: int = 16000
    silence_threshold: float = 0.01  # 0.0 – 1.0 amplitude
    silence_seconds: float = 1.2  # end-of-utterance timeout

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}STT_", extra="ignore")


class TTSSettings(BaseSettings):
    """Cross-provider TTS knobs.

    Provider-*specific* settings (API keys, model paths, voice ids that
    only make sense for one backend) live in their own settings blocks
    below (``PiperSettings``, ``KokoroSettings``, ``EdgeTTSSettings``,
    ``ElevenLabsSettings``) and in ``OpenAISettings``. Switching
    ``backend`` is the only thing that changes which adapter
    :func:`build_tts_provider` returns — no other code changes.
    """

    enabled: bool = True
    backend: TTSBackend = TTSBackend.PIPER
    voice: str = "alloy"
    model: str = "tts-1"
    format: Literal["mp3", "wav", "opus", "aac", "flac"] = "mp3"
    speak_replies: bool = False  # auto-speak assistant replies
    playback_speed: float = 1.0
    pitch: float = 1.0  # 1.0 = natural pitch
    volume: float = 1.0  # 0.0 - 2.0 linear gain
    streaming: bool = True  # start speaking before full text is synthesized

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}TTS_", extra="ignore")


class PiperSettings(BaseSettings):
    """Primary offline TTS — fully local, no network/API key required."""

    enabled: bool = True
    voice: str = "en_US-lessac-medium"
    model_path: str = ""  # optional explicit .onnx path
    executable: str = "piper"  # binary name/path if not on PATH
    sample_rate: int = 22050

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}PIPER_", extra="ignore")


class KokoroSettings(BaseSettings):
    """Optional offline TTS with more natural prosody than Piper."""

    enabled: bool = False
    voice: str = "af_heart"
    model_path: str = ""
    language: str = "en-us"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}KOKORO_", extra="ignore")


class EdgeTTSSettings(BaseSettings):
    """Free, online, Microsoft-hosted neural TTS with true streaming."""

    enabled: bool = True
    voice: str = "en-US-AriaNeural"
    rate: str = "+0%"  # edge-tts SSML-ish rate string
    pitch_hz: str = "+0Hz"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}EDGE_TTS_", extra="ignore")


class ElevenLabsSettings(BaseSettings):
    """Premium online TTS — most natural voices, paid API."""

    enabled: bool = False
    api_key: SecretStr = SecretStr("")
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # "Rachel"
    model: str = "eleven_turbo_v2_5"
    base_url: str = "https://api.elevenlabs.io"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}ELEVENLABS_", extra="ignore")


class VoiceSettings(BaseSettings):
    """Cross-cutting voice settings that don't belong to a single provider."""

    mode: VoiceMode = VoiceMode.PUSH_TO_TALK
    push_to_talk_hotkey: str = "ctrl+space"
    toggle_hotkey: str = "ctrl+alt+space"
    input_device: str = ""  # empty → system default
    output_device: str = ""  # empty → system default

    # Continuous, hands-free conversation: after JARVIS finishes speaking
    # it automatically starts listening again (mic-hold/toggle no longer
    # needed for each turn). Ends when the user says nothing for
    # ``silence_seconds`` (see STTSettings) or explicitly stops it.
    continuous_conversation: bool = False

    # Interrupt support: while JARVIS is speaking, keep the microphone
    # "warm" (VAD-only, not full recording) so that if the user starts
    # talking, playback is cancelled immediately and a real recording
    # begins — no need to press a hotkey to interrupt.
    interrupt_enabled: bool = True
    interrupt_vad_threshold: float = 0.02  # RMS amplitude that counts as "user is talking"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}VOICE_", extra="ignore")


class WakeWordSettings(BaseSettings):
    enabled: bool = False
    engine: WakeWordEngine = WakeWordEngine.NONE
    keywords: list[str] = Field(default_factory=lambda: ["jarvis"])
    sensitivity: float = 0.5
    model_path: str = ""  # optional custom model (.ppn/.onnx path)
    access_key: SecretStr = SecretStr("")  # Porcupine AccessKey, if that engine is used

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}WAKE_", extra="ignore")

    @field_validator("keywords", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


class HotkeySettings(BaseSettings):
    enabled: bool = True
    toggle_window: str = "ctrl+alt+j"  # show/hide main window
    tray_show: str = ""  # optional extra combo

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}HOTKEY_", extra="ignore")


class BrowserSettings(BaseSettings):
    enabled: bool = True
    engine: Literal["chromium", "firefox", "webkit"] = "chromium"
    headless: bool = False
    user_data_dir: Path = Path("./data/cache/playwright")

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}BROWSER_", extra="ignore")


class WindowsAutomationSettings(BaseSettings):
    enabled: bool = True
    backend: Literal["uia", "win32"] = "uia"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}WIN_AUTOMATION_", extra="ignore")


class AutomationSettings(BaseSettings):
    """Tunables for the AI Automation Engine (Milestone 4).

    These govern the *engine* (parser/planner/executor/safety); OS- and
    browser-specific knobs stay in :class:`WindowsAutomationSettings` and
    :class:`BrowserSettings` respectively.
    """

    enabled: bool = True
    max_retries: int = 2
    retry_backoff_seconds: float = 1.5
    confirmation_timeout_seconds: float = 60.0
    # If no confirmation callback is supplied (e.g. headless/voice-only
    # flows) and an action needs one, default to denying rather than
    # silently proceeding.
    auto_deny_when_unconfirmable: bool = True
    history_retention_days: int = 90
    undo_stack_size: int = 50
    # Milestone 7, Phase 1: ceiling on how many dependency-satisfied
    # ("independent") steps ActionExecutor.run_plan() may dispatch
    # concurrently once Phase 2 wires it up. Additive default (4) --
    # Phase 1 declares this setting only; run_plan() still executes
    # every plan sequentially until Phase 2 lands, so this value has no
    # observable effect yet.
    max_parallel_steps: int = 4

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}AUTOMATION_", extra="ignore")


class AgentSettings(BaseSettings):
    max_steps: int = 25
    timeout_seconds: int = 180
    checkpoint_enabled: bool = True
    # Milestone 7, Phase 1: same purpose as
    # AutomationSettings.max_parallel_steps, for the LangGraph agent
    # runtime's own tool-call dispatch. Read by ``agents/nodes/
    # tool_executor.py`` since Milestone 10 AC1, which absorbed the
    # deferred M7 Phase 3 cross-tool-parallelism scope.
    max_parallel_steps: int = 4
    # Milestone 10 AC3 (interim Permission Validation -- see
    # agents/permission.py): tool names that always require an explicit
    # confirmation before the agent may call them. "run_automation" is the
    # only tool in the registry today capable of a destructive action;
    # AutomationService's own PermissionGate still gates it internally too
    # -- this is the *outer*, graph-visible gate every tool call now also
    # passes through, not a replacement for that inner one.
    confirm_required_tools: frozenset[str] = frozenset({"run_automation"})

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}AGENT_", extra="ignore")


class SchedulerSettings(BaseSettings):
    """Tunables for the cron/interval job scheduler (Milestone 7, Phase 6).

    Declared in Phase 1 for forward compatibility only -- no scheduler
    loop exists yet, so nothing reads these values until Phase 6.
    """

    enabled: bool = True
    poll_interval_seconds: float = 30.0
    max_concurrent_jobs: int = 2

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}SCHEDULER_", extra="ignore")


class UISettings(BaseSettings):
    theme: ThemeName = ThemeName.JARVIS
    accent: str = "#00E5FF"
    start_minimized: bool = False
    hotkey_toggle: str = "ctrl+alt+j"
    streaming_mode: StreamingMode = StreamingMode.TYPEWRITER
    system_prompt: str = "You are JARVIS, a concise and helpful personal AI operating system."

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}UI_", extra="ignore")


class SecuritySettings(BaseSettings):
    secret_key: SecretStr = SecretStr("CHANGE_ME_TO_A_FERNET_KEY")
    use_os_keyring: bool = True

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}", extra="ignore")


class DeveloperModeSettings(BaseSettings):
    """Milestone 5 -- gates Developer Mode behind an admin password.

    JARVIS itself never requires a password to launch; only the Developer
    Mode shell (API Center, Update Center, Module/Plugin managers, ...)
    checks ``password_hash``. Empty hash means "not yet configured" --
    the gate dialog then asks the user to set one instead of unlocking.
    """

    enabled: bool = True
    password_hash: SecretStr = SecretStr("")
    session_timeout_minutes: int = 30

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}DEV_MODE_", extra="ignore")


class UpdateSettings(BaseSettings):
    """Milestone 5 -- Update Center tunables (mock update service)."""

    channel: Literal["stable", "beta", "developer", "nightly"] = "stable"
    auto_check: bool = True
    check_interval_hours: int = 24
    create_restore_point: bool = True

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}UPDATE_", extra="ignore")


class VoiceAnnouncementSettings(BaseSettings):
    """Milestone 5 -- AI Voice Announcements during updates (mock TTS)."""

    enabled: bool = True
    style: Literal["formal", "friendly", "concise"] = "formal"
    volume: float = 0.8
    speed: float = 1.0
    language: str = "en-US"

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}VOICE_ANNOUNCE_", extra="ignore")


class VisionSettings(BaseSettings):
    """Milestone 6 -- Vision & Multimodal (Phase 2: configuration scaffolding only).

    No provider exists yet; ``enabled`` defaults to ``False`` and has no
    functional effect until a real provider is wired in a later phase.
    """

    enabled: bool = False

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}VISION_", extra="ignore")


class OCRSettings(BaseSettings):
    """Milestone 6 -- Vision & Multimodal (Phase 2: configuration scaffolding only).

    No provider exists yet; ``enabled`` defaults to ``False`` and has no
    functional effect until a real provider is wired in a later phase.
    """

    enabled: bool = False

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}OCR_", extra="ignore")


class ResourceSettings(BaseSettings):
    """Milestone 9 Task Group C -- Resource Manager budget thresholds.

    Tracking/alerting only (``ResourceManager`` publishes
    ``ResourceBudgetExceededEvent`` on a crossing) -- nothing throttles
    or kills a service on a budget breach yet; that's M22 Edge AI
    Platform's future Resource Allocation module, not this milestone.
    """

    max_cpu_percent: float = 90.0
    max_memory_mb: float = 4096.0

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}RESOURCE_", extra="ignore")


class PluginSettings(BaseSettings):
    """Milestone 9 Task Group D -- Plugin Platform.

    ``sandbox_mode`` is this platform's *default* tier (Phase 3); an
    individual plugin's manifest can still request the other tier --
    this only sets what a plugin gets when it doesn't ask.
    ``allow_unsigned_packages`` mirrors the roadmap's own "no hosted
    infra for v1" position (Phase 7) -- true by default so local/
    community plugins remain installable before a real signing
    authority exists, not because signatures don't matter.
    """

    enabled: bool = True
    sandbox_mode: str = "in_process"
    hook_timeout_seconds: float = 10.0
    max_cpu_percent: float = 50.0
    max_memory_mb: float = 512.0
    allow_unsigned_packages: bool = True
    marketplace_index_path: str = ""

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}PLUGINS_", extra="ignore")


class DevToolsSettings(BaseSettings):
    """Milestone 9 Task Group E -- Developer Platform Tools.

    Separate from ``DeveloperModeSettings`` (M5's password-gated UI
    shell) -- this gates real backend instrumentation (a loguru sink,
    an HTTP middleware) that has a genuine, if small, per-request/
    per-log-line cost, not just a UI panel's visibility. Defaults on
    (``debug_console_enabled=True``) since this whole milestone is a
    developer-facing, opt-out-if-you-must tool, not a hardened
    production data path.
    """

    debug_console_enabled: bool = True
    debug_console_level: str = "INFO"
    debug_console_max_entries: int = 2000
    performance_history_size: int = 240
    api_inspector_enabled: bool = True
    api_inspector_max_records: int = 500

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX}DEVTOOLS_", extra="ignore")


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """Root settings object — inject via DI, never instantiate ad-hoc."""

    env: Environment = Environment.DEVELOPMENT
    debug: bool = True
    app_name: str = "JARVIS OS"
    app_version: str = "0.14.0"
    data_dir: Path | None = None

    llm_default_provider: LLMProviderName = LLMProviderName.OLLAMA
    # Optional secondary provider used only if the default provider's call
    # fails (timeout, rate-limit, connection error) — "use only when
    # necessary" rather than load-balanced or preferred.
    llm_fallback_provider: LLMProviderName | None = None

    log: LoggingSettings = Field(default_factory=LoggingSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    vector: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    piper: PiperSettings = Field(default_factory=PiperSettings)
    kokoro: KokoroSettings = Field(default_factory=KokoroSettings)
    edge_tts: EdgeTTSSettings = Field(default_factory=EdgeTTSSettings)
    elevenlabs: ElevenLabsSettings = Field(default_factory=ElevenLabsSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    wake: WakeWordSettings = Field(default_factory=WakeWordSettings)
    hotkey: HotkeySettings = Field(default_factory=HotkeySettings)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    win_automation: WindowsAutomationSettings = Field(default_factory=WindowsAutomationSettings)
    automation: AutomationSettings = Field(default_factory=AutomationSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    ui: UISettings = Field(default_factory=UISettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    dev_mode: DeveloperModeSettings = Field(default_factory=DeveloperModeSettings)
    update: UpdateSettings = Field(default_factory=UpdateSettings)
    voice_announce: VoiceAnnouncementSettings = Field(default_factory=VoiceAnnouncementSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    ocr: OCRSettings = Field(default_factory=OCRSettings)
    resource: ResourceSettings = Field(default_factory=ResourceSettings)
    plugins: PluginSettings = Field(default_factory=PluginSettings)
    devtools: DevToolsSettings = Field(default_factory=DevToolsSettings)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Cross-field validation
    # ------------------------------------------------------------------
    def check(self) -> Settings:
        """Validate that at least one LLM provider is enabled and reachable in config."""
        default = self.llm_default_provider
        if default is LLMProviderName.OPENAI and not self.openai.enabled:
            raise ConfigError("JARVIS_LLM_DEFAULT_PROVIDER=openai but JARVIS_OPENAI_ENABLED=false.")
        if default is LLMProviderName.OLLAMA and not self.ollama.enabled:
            raise ConfigError("JARVIS_LLM_DEFAULT_PROVIDER=ollama but JARVIS_OLLAMA_ENABLED=false.")
        if default is LLMProviderName.GEMINI and not self.gemini.enabled:
            raise ConfigError("JARVIS_LLM_DEFAULT_PROVIDER=gemini but JARVIS_GEMINI_ENABLED=false.")
        if not (self.openai.enabled or self.ollama.enabled or self.gemini.enabled):
            raise ConfigError("At least one LLM provider must be enabled.")
        if self.openai.enabled and not self.openai.api_key.get_secret_value():
            raise ConfigError("JARVIS_OPENAI_ENABLED=true but JARVIS_OPENAI_API_KEY is empty.")
        if self.gemini.enabled and not self.gemini.api_key.get_secret_value():
            raise ConfigError("JARVIS_GEMINI_ENABLED=true but JARVIS_GEMINI_API_KEY is empty.")
        if self.llm_fallback_provider is LLMProviderName.GEMINI and not self.gemini.enabled:
            raise ConfigError(
                "JARVIS_LLM_FALLBACK_PROVIDER=gemini but JARVIS_GEMINI_ENABLED=false."
            )
        return self

    # ------------------------------------------------------------------
    # Derived paths
    # ------------------------------------------------------------------
    @property
    def resolved_data_dir(self) -> Path:
        return _paths.resolve_data_dir(self.data_dir)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_settings(env_file: Path | str | None = None) -> Settings:
    """Load, validate and cache the :class:`Settings` object.

    * Reads ``env_file`` if provided, otherwise the default ``.env`` lookup
      performed by pydantic-settings applies.
    * Creates the runtime directories.
    * Runs cross-field validation via :meth:`Settings.check`.

    Crash-recovery (RC1, section 6): a corrupted ``.env`` file -- e.g.
    binary garbage left by a power loss mid-write -- previously crashed
    startup with an uncaught ``UnicodeDecodeError`` before a single log
    line could even be written. Falls back to defaults (OS environment
    variables + built-in defaults, skipping only the unreadable file)
    instead, so a corrupted local config file can't prevent the app
    from starting at all.
    """
    try:
        if env_file is not None:
            settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
        else:
            settings = Settings()
    except (UnicodeDecodeError, ValueError) as err:
        import sys

        print(
            f"WARNING: could not read .env config ({err!r}); "
            f"starting with defaults instead of crashing.",
            file=sys.stderr,
        )
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
    settings = settings.check()
    _paths.ensure_runtime_dirs(settings.resolved_data_dir)
    return settings
