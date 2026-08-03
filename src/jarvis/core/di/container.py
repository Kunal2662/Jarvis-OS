"""Application-wide DI container.

We use `dependency-injector <https://python-dependency-injector.ets-labs.org>`_
because it plays well with both PySide6 (sync) and FastAPI/asyncio (async).

Adapters, and the handful of services with heavy or platform-specific
transitive imports (``conversation_service``, ``memory_service``,
``automation_service``, ``agent_orchestrator``), are constructed lazily
inside ``_build_*`` factory callables so:

* importing :mod:`jarvis.core.di.container` stays cheap and side-effect-free;
* platform-specific dependencies (``pywinauto``, ``pynput``, ``sounddevice``)
  only fail on real use, not on import;
* heavy runtime stacks (LangGraph/LangChain/LangSmith, pulled in by
  ``agent_orchestrator``) are only imported the first time that provider is
  actually resolved, not at container-declaration time.

Every other application service is still registered via
``dependency_injector``'s string-path form (e.g.
``providers.Singleton("jarvis.services.x.X", ...)``). Note that this form
resolves and imports its target *eagerly*, at class-declaration time — not
lazily as the name might suggest. That's fine for the services left in this
form: none of them import anything beyond the shared configuration/logging
baseline that the container pays for anyway via ``settings``. Only convert a
service to the ``_build_*`` callable form above if it's confirmed (by
measuring, not guessing) to pull in something heavy or platform-specific.
"""

from __future__ import annotations

from typing import Any

from dependency_injector import containers, providers

from jarvis.core.config.settings import Settings


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------
def _build_llm_provider(settings: Settings) -> Any:
    from jarvis.infrastructure.llm.provider_factory import build_llm_provider

    primary = build_llm_provider(
        settings.llm_default_provider,
        openai_settings=settings.openai,
        ollama_settings=settings.ollama,
        gemini_settings=settings.gemini,
    )

    fallback_name = settings.llm_fallback_provider
    if fallback_name is None or fallback_name is settings.llm_default_provider:
        return primary

    from jarvis.infrastructure.llm.fallback_provider import FallbackLLMProvider

    fallback = build_llm_provider(
        fallback_name,
        openai_settings=settings.openai,
        ollama_settings=settings.ollama,
        gemini_settings=settings.gemini,
    )
    return FallbackLLMProvider(primary, fallback)


def _build_stt_provider(settings: Settings) -> Any:
    from jarvis.infrastructure.stt.provider_factory import build_stt_provider

    return build_stt_provider(settings.stt, settings.openai)


def _build_tts_provider(settings: Settings) -> Any:
    from jarvis.infrastructure.tts.provider_factory import build_tts_provider

    return build_tts_provider(settings)


def _build_vision_provider(settings: Settings) -> Any:
    from jarvis.infrastructure.vision.provider_factory import build_vision_provider

    return build_vision_provider(settings.vision)


def _build_ocr_provider(settings: Settings) -> Any:
    from jarvis.infrastructure.ocr.provider_factory import build_ocr_provider

    return build_ocr_provider(settings.ocr)


def _build_wake_word_detector(settings: Settings) -> Any:
    from jarvis.infrastructure.wake_word.provider_factory import build_wake_word_detector

    return build_wake_word_detector(settings.wake)


def _build_audio_recorder(settings: Settings) -> Any:
    from jarvis.infrastructure.audio.sounddevice_recorder import SoundDeviceRecorder

    return SoundDeviceRecorder(settings.stt, settings.voice)


def _build_audio_player(settings: Settings) -> Any:
    from jarvis.infrastructure.audio.sounddevice_player import SoundDevicePlayer

    return SoundDevicePlayer(settings.tts, settings.voice)


def _build_hotkey_listener(settings) -> Any:
    from jarvis.infrastructure.hotkey.pynput_listener import PynputHotkeyListener

    return PynputHotkeyListener()


def _build_vector_store(settings: Settings) -> Any:
    from jarvis.infrastructure.vectorstore.chroma_client import ChromaVectorStore

    return ChromaVectorStore(settings.vector)


def _build_database(settings: Settings) -> Any:
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    return SQLiteDatabase(settings.db)


def _build_browser(settings: Settings) -> Any:
    from jarvis.infrastructure.browser.playwright_adapter import PlaywrightBrowser

    return PlaywrightBrowser(settings.browser)


def _build_os_automation(settings: Settings) -> Any:
    import sys

    if sys.platform.startswith("win") and settings.win_automation.enabled:
        from jarvis.infrastructure.automation.windows_adapter import (
            WindowsAutomationAdapter,
        )

        return WindowsAutomationAdapter(settings.win_automation)

    from jarvis.infrastructure.automation.noop_adapter import NoopAutomationAdapter

    return NoopAutomationAdapter()


def _build_memory_recall_hook(settings) -> Any:
    """Legacy no-op factory — kept for the standalone import path.

    The real hook is provided by the container as a
    ``SemanticMemoryRecallHook`` singleton wired to ``memory_service``.
    """
    from jarvis.core.interfaces.memory import NoopMemoryRecall

    return NoopMemoryRecall()


def _build_conversation_service(database: Any) -> Any:
    from jarvis.services.conversation_service import ConversationService

    return ConversationService(database=database)


def _build_memory_service(database: Any, vector_store: Any, llm: Any, settings: Settings) -> Any:
    from jarvis.services.memory_service import MemoryService

    return MemoryService(database=database, vector_store=vector_store, llm=llm, settings=settings)


def _build_automation_service(
    os_automation: Any,
    settings: Settings,
    browser_service: Any,
    database: Any,
    event_bus: Any,
) -> Any:
    from jarvis.services.automation_service import AutomationService

    return AutomationService(
        os_automation=os_automation,
        settings=settings,
        browser_service=browser_service,
        database=database,
        event_bus=event_bus,
    )


def _build_agent_orchestrator(
    *,
    settings: Settings,
    llm: Any,
    memory: Any,
    automation: Any,
    browser: Any,
    chat: Any,
    voice: Any,
    system: Any,
    vision: Any,
    event_bus: Any,
) -> Any:
    from jarvis.agents.orchestrator import AgentOrchestrator

    return AgentOrchestrator(
        settings=settings,
        llm=llm,
        memory=memory,
        automation=automation,
        browser=browser,
        chat=chat,
        voice=voice,
        system=system,
        vision=vision,
        event_bus=event_bus,
    )


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------
class Container(containers.DeclarativeContainer):
    """The single, application-wide DI container."""

    # ---- Configuration -------------------------------------------------
    config = providers.Configuration()
    settings: providers.Singleton[Settings] = providers.Singleton(Settings)

    # ---- Cross-cutting -------------------------------------------------
    event_bus = providers.Singleton("jarvis.core.events.event_bus.EventBus")
    runtime_manager = providers.Singleton("jarvis.core.lifecycle.runtime_manager.RuntimeManager")

    # ---- Infrastructure adapters (Singletons) --------------------------
    llm_provider = providers.Singleton(_build_llm_provider, settings=settings)
    stt_provider = providers.Singleton(_build_stt_provider, settings=settings)
    tts_provider = providers.Singleton(_build_tts_provider, settings=settings)
    vision_provider = providers.Singleton(_build_vision_provider, settings=settings)
    ocr_provider = providers.Singleton(_build_ocr_provider, settings=settings)
    audio_recorder = providers.Singleton(_build_audio_recorder, settings=settings)
    audio_player = providers.Singleton(_build_audio_player, settings=settings)
    wake_word_detector = providers.Singleton(_build_wake_word_detector, settings=settings)
    hotkey_listener = providers.Singleton(_build_hotkey_listener, settings=settings)
    vector_store = providers.Singleton(_build_vector_store, settings=settings)
    database = providers.Singleton(_build_database, settings=settings)
    browser = providers.Singleton(_build_browser, settings=settings)
    os_automation = providers.Singleton(_build_os_automation, settings=settings)
    memory_recall_hook = providers.Singleton(_build_memory_recall_hook, settings=settings)

    # ---- Application services -----------------------------------------
    settings_service = providers.Singleton(
        "jarvis.services.settings_service.SettingsService",
        settings=settings,
    )
    theme_service = providers.Singleton(
        "jarvis.services.theme_service.ThemeService",
        settings=settings,
    )
    conversation_service = providers.Singleton(
        _build_conversation_service,
        database=database,
    )
    memory_service = providers.Singleton(
        _build_memory_service,
        database=database,
        vector_store=vector_store,
        llm=llm_provider,
        settings=settings,
    )
    memory_recall_hook = providers.Singleton(
        "jarvis.services.semantic_memory_recall_hook.SemanticMemoryRecallHook",
        memory_service=memory_service,
    )
    chat_service = providers.Singleton(
        "jarvis.services.chat_service.ChatService",
        llm=llm_provider,
        conversations=conversation_service,
        settings=settings,
        memory_recall=memory_recall_hook,
    )
    voice_service = providers.Singleton(
        "jarvis.services.voice_service.VoiceService",
        stt=stt_provider,
        tts=tts_provider,
        recorder=audio_recorder,
        player=audio_player,
        settings=settings,
        wake_word=wake_word_detector,
        event_bus=event_bus,
    )
    hotkey_service = providers.Singleton(
        "jarvis.services.hotkey_service.HotkeyService",
        listener=hotkey_listener,
        settings=settings,
    )
    browser_service = providers.Factory(
        "jarvis.services.browser_service.BrowserService",
        browser=browser,
        settings=settings,
    )
    automation_service = providers.Factory(
        _build_automation_service,
        os_automation=os_automation,
        settings=settings,
        browser_service=browser_service,
        database=database,
        event_bus=event_bus,
    )
    system_service = providers.Factory(
        "jarvis.services.system_service.SystemService",
        settings=settings,
    )
    vision_service = providers.Singleton(
        "jarvis.services.vision_service.VisionService",
        vision=vision_provider,
        ocr=ocr_provider,
        settings=settings,
    )

    # ---- Milestone 5 -- UI / Developer Mode / API Center / Update Center --
    api_center_service = providers.Singleton(
        "jarvis.services.api_center_service.ApiCenterService",
        settings=settings,
    )
    developer_mode_service = providers.Singleton(
        "jarvis.services.developer_mode_service.DeveloperModeService",
        settings=settings,
        settings_service=settings_service,
    )
    voice_announcement_service = providers.Singleton(
        "jarvis.services.voice_announcement_service.VoiceAnnouncementService",
        settings=settings,
        voice_service=voice_service,
    )
    update_service = providers.Singleton(
        "jarvis.services.update_service.UpdateService",
        settings=settings,
        event_bus=event_bus,
        voice_announcer=voice_announcement_service,
    )
    greeting_service = providers.Singleton(
        "jarvis.services.greeting_service.GreetingService",
        settings=settings,
        llm_provider=llm_provider,
        memory_service=memory_service,
        conversation_service=conversation_service,
    )

    # ---- Agents (Milestone 5-Agents) ------------------------------------
    agent_orchestrator = providers.Singleton(
        _build_agent_orchestrator,
        settings=settings,
        llm=llm_provider,
        memory=memory_service,
        automation=automation_service,
        browser=browser_service,
        chat=chat_service,
        voice=voice_service,
        system=system_service,
        vision=vision_service,
        event_bus=event_bus,
    )
