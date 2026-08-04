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


def _build_memory_service(
    database: Any, vector_store: Any, llm: Any, settings: Settings, event_bus: Any
) -> Any:
    from jarvis.services.memory_service import MemoryService

    return MemoryService(
        database=database,
        vector_store=vector_store,
        llm=llm,
        settings=settings,
        event_bus=event_bus,
    )


def _build_knowledge_service(
    database: Any, vector_store: Any, llm: Any, memory: Any, event_bus: Any
) -> Any:
    from jarvis.services.knowledge_service import KnowledgeService

    return KnowledgeService(
        database=database, vector_store=vector_store, llm=llm, memory=memory, event_bus=event_bus
    )


def _build_intelligence_service(database: Any, memory: Any, event_bus: Any) -> Any:
    from jarvis.services.intelligence_service import IntelligenceService

    return IntelligenceService(database=database, memory=memory, event_bus=event_bus)


def _build_search_service(
    memory_service: Any,
    knowledge_service: Any,
    intelligence_service: Any,
    automation_service: Any,
    browser_service: Any,
    system_service: Any,
    voice_service: Any,
    chat_service: Any,
    vision_service: Any,
    plugin_registry: Any,
) -> Any:
    """Wires the Search Provider Registry (Milestone 10A, Additional
    Requirement #1): resolves the *existing* Tool Registry and Plugin
    Registry once, here at the composition root, and registers one
    ``ISearchSource`` per subsystem -- ``SearchService`` itself never
    imports ``agents`` or ``core.plugins`` directly (see
    ``services/search_sources.py``'s own module docstring for why)."""
    from jarvis.agents.tools import build_tool_registry
    from jarvis.services.search_service import SearchService
    from jarvis.services.search_sources import (
        CommandSearchSource,
        GoalSearchSource,
        KnowledgeSearchSource,
        MemorySearchSource,
    )

    tools = build_tool_registry(
        memory=memory_service,
        automation=automation_service,
        browser=browser_service,
        system=system_service,
        voice=voice_service,
        chat=chat_service,
        vision=vision_service,
    )
    tool_descriptions = [(t.name, t.description) for t in tools]

    service = SearchService()
    service.register_source(MemorySearchSource(memory_service))
    service.register_source(KnowledgeSearchSource(knowledge_service))
    service.register_source(GoalSearchSource(intelligence_service))
    service.register_source(CommandSearchSource(tool_descriptions, plugin_registry=plugin_registry))
    return service


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


def _build_service_manager(
    *,
    event_bus: Any,
    conversation_service: Any,
    chat_service: Any,
    memory_service: Any,
    theme_service: Any,
    settings: Settings,
) -> Any:
    from jarvis.core.lifecycle.service_manager import (
        ChatServiceAdapter,
        ConversationServiceAdapter,
        MemoryServiceAdapter,
        ServiceManager,
        ThemeServiceAdapter,
    )

    manager = ServiceManager(event_bus=event_bus)
    manager.register("conversation", ConversationServiceAdapter(conversation_service), priority=10)
    manager.register(
        "chat", ChatServiceAdapter(chat_service), dependencies=("conversation",), priority=20
    )
    manager.register(
        "memory",
        MemoryServiceAdapter(memory_service, enabled=settings.memory.enabled),
        priority=10,
    )
    manager.register("theme", ThemeServiceAdapter(theme_service), priority=10)
    return manager


def _build_resource_manager(*, event_bus: Any, settings: Settings) -> Any:
    from jarvis.core.lifecycle.resource_manager import ResourceManager

    manager = ResourceManager(event_bus=event_bus)
    manager.register_budget("cpu", "cpu_percent", settings.resource.max_cpu_percent)
    manager.register_budget(
        "memory", "memory_rss_bytes", settings.resource.max_memory_mb * 1024 * 1024
    )
    return manager


def _build_plugin_loader(*, settings: Settings, platform_adapter: Any) -> Any:
    from jarvis.core.config import paths as _paths
    from jarvis.core.plugins.loader import PluginLoader

    return PluginLoader(
        _paths.plugins_dir(settings.resolved_data_dir),
        platform_adapter=platform_adapter,
        app_version=settings.app_version,
    )


def _build_plugin_sandbox(*, settings: Settings) -> Any:
    from jarvis.core.plugins.sandbox import PluginSandbox

    return PluginSandbox(hook_timeout_seconds=settings.plugins.hook_timeout_seconds)


def _build_permission_model(*, event_bus: Any, settings: Settings) -> Any:
    from jarvis.core.config import paths as _paths
    from jarvis.core.plugins.permissions import PermissionModel

    return PermissionModel(
        event_bus,
        store_path=_paths.config_dir(settings.resolved_data_dir) / "plugin_permissions.json",
    )


def _build_plugin_registry(
    *,
    plugin_loader: Any,
    plugin_sandbox: Any,
    permission_model: Any,
    event_bus: Any,
    platform_adapter: Any,
    settings: Settings,
    hotkey_service: Any,
) -> Any:
    from jarvis.core.plugins.registry import PluginRegistry

    return PluginRegistry(
        loader=plugin_loader,
        sandbox=plugin_sandbox,
        permission_model=permission_model,
        event_bus=event_bus,
        platform_adapter=platform_adapter,
        plugin_data_root=settings.resolved_data_dir / "plugin-data",
        hotkey_service=hotkey_service,
    )


def _build_mcp_server_runtime(*, permission_model: Any, event_bus: Any, settings: Settings) -> Any:
    from jarvis.core.mcp.server import MCPServerRuntime

    return MCPServerRuntime(
        permission_model=permission_model,
        event_bus=event_bus,
        server_id=settings.mcp.server_id,
    )


def _build_mcp_client_runtime(*, event_bus: Any, settings: Settings) -> Any:
    from jarvis.core.mcp.client import MCPClientRuntime

    return MCPClientRuntime(
        event_bus=event_bus,
        client_id=settings.mcp.server_id,
        reconnect_attempts=settings.mcp.reconnect_attempts,
        reconnect_backoff_seconds=settings.mcp.reconnect_backoff_seconds,
    )


def _build_mcp_transport_registry() -> Any:
    """Empty of network transports by design -- ``stdio``/``websocket``/
    ``http``/``ipc`` each register here in their own later task group
    (M10.5 Task Group A ships the abstraction, not the transports)."""
    from jarvis.core.mcp.transport import TransportFactoryRegistry

    return TransportFactoryRegistry()


def _build_plugin_store(*, plugin_registry: Any, settings: Settings) -> Any:
    from jarvis.core.plugins.store import PluginStore, UnsignedAllowedVerifier

    return PluginStore(
        plugin_registry,
        staging_dir=settings.resolved_data_dir / "cache" / "plugin_staging",
        signature_verifier=UnsignedAllowedVerifier(
            allow_unsigned=settings.plugins.allow_unsigned_packages
        ),
    )


def _build_marketplace(*, settings: Settings) -> Any:
    from pathlib import Path

    from jarvis.core.config import paths as _paths
    from jarvis.core.plugins.marketplace import LocalPluginRepository, Marketplace

    configured = settings.plugins.marketplace_index_path
    index_path = (
        Path(configured)
        if configured
        else _paths.config_dir(settings.resolved_data_dir) / "marketplace_index.json"
    )
    return Marketplace(LocalPluginRepository(index_path))


def _build_debug_console(*, event_bus: Any, settings: Settings) -> Any:
    from jarvis.core.devtools.debug_console import DebugConsole

    return DebugConsole(event_bus, max_entries=settings.devtools.debug_console_max_entries)


def _build_performance_profiler(*, event_bus: Any, settings: Settings) -> Any:
    from jarvis.core.devtools.performance_profiler import PerformanceProfiler

    return PerformanceProfiler(event_bus, history_size=settings.devtools.performance_history_size)


def _build_api_inspector(*, settings: Settings) -> Any:
    from jarvis.core.devtools.api_inspector import ApiInspector

    return ApiInspector(max_records=settings.devtools.api_inspector_max_records)


def _build_state_inspector(
    *, service_manager: Any, plugin_registry: Any, runtime_manager: Any
) -> Any:
    from jarvis.core.devtools.state_inspector import StateInspector

    return StateInspector(
        service_manager=service_manager,
        plugin_registry=plugin_registry,
        runtime_manager=runtime_manager,
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
    knowledge: Any,
    intelligence: Any,
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
        knowledge=knowledge,
        intelligence=intelligence,
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
    runtime_manager = providers.Singleton(
        "jarvis.core.lifecycle.runtime_manager.RuntimeManager",
        event_bus=event_bus,
    )
    configuration_manager = providers.Singleton(
        "jarvis.core.lifecycle.configuration_manager.ConfigurationManager",
        settings=settings,
        event_bus=event_bus,
    )
    crash_recovery_manager = providers.Singleton(
        "jarvis.core.lifecycle.crash_recovery.CrashRecoveryManager",
        settings=settings,
        event_bus=event_bus,
    )

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
    session_manager = providers.Singleton(
        "jarvis.core.lifecycle.session_manager.SessionManager",
        database=database,
        event_bus=event_bus,
    )

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
        event_bus=event_bus,
    )
    knowledge_service = providers.Singleton(
        _build_knowledge_service,
        database=database,
        vector_store=vector_store,
        llm=llm_provider,
        memory=memory_service,
        event_bus=event_bus,
    )
    intelligence_service = providers.Singleton(
        _build_intelligence_service,
        database=database,
        memory=memory_service,
        event_bus=event_bus,
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
    service_manager = providers.Singleton(
        _build_service_manager,
        event_bus=event_bus,
        conversation_service=conversation_service,
        chat_service=chat_service,
        memory_service=memory_service,
        theme_service=theme_service,
        settings=settings,
    )
    health_monitor = providers.Singleton(
        "jarvis.core.lifecycle.health_monitor.HealthMonitor",
        service_manager=service_manager,
        event_bus=event_bus,
    )
    runtime_ws_hub = providers.Singleton(
        "jarvis.core.lifecycle.runtime_ws_hub.RuntimeWebSocketHub",
        event_bus=event_bus,
        session_manager=session_manager,
    )
    background_task_manager = providers.Singleton(
        "jarvis.core.lifecycle.background_task_manager.BackgroundTaskManager",
        event_bus=event_bus,
    )
    resource_manager = providers.Singleton(
        _build_resource_manager,
        event_bus=event_bus,
        settings=settings,
    )

    # ---- Milestone 9 Task Group D -- Plugin Platform --------------------
    platform_adapter = providers.Singleton(
        "jarvis.infrastructure.platform.adapter.DefaultPlatformAdapter",
    )
    plugin_loader = providers.Singleton(
        _build_plugin_loader,
        settings=settings,
        platform_adapter=platform_adapter,
    )
    plugin_sandbox = providers.Singleton(
        _build_plugin_sandbox,
        settings=settings,
    )
    permission_model = providers.Singleton(
        _build_permission_model,
        event_bus=event_bus,
        settings=settings,
    )
    plugin_registry = providers.Singleton(
        _build_plugin_registry,
        plugin_loader=plugin_loader,
        plugin_sandbox=plugin_sandbox,
        permission_model=permission_model,
        event_bus=event_bus,
        platform_adapter=platform_adapter,
        settings=settings,
        hotkey_service=hotkey_service,
    )
    plugin_store = providers.Singleton(
        _build_plugin_store,
        plugin_registry=plugin_registry,
        settings=settings,
    )
    marketplace = providers.Singleton(
        _build_marketplace,
        settings=settings,
    )

    # ---- Milestone 10.5 Task Group A -- MCP & Integration Platform --------
    mcp_transport_registry = providers.Singleton(_build_mcp_transport_registry)
    mcp_server_runtime = providers.Singleton(
        _build_mcp_server_runtime,
        permission_model=permission_model,
        event_bus=event_bus,
        settings=settings,
    )
    mcp_client_runtime = providers.Singleton(
        _build_mcp_client_runtime,
        event_bus=event_bus,
        settings=settings,
    )

    # ---- Milestone 10A -- Universal Search & Knowledge Platform ------------
    search_service = providers.Singleton(
        _build_search_service,
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        intelligence_service=intelligence_service,
        automation_service=automation_service,
        browser_service=browser_service,
        system_service=system_service,
        voice_service=voice_service,
        chat_service=chat_service,
        vision_service=vision_service,
        plugin_registry=plugin_registry,
    )

    # ---- Milestone 9 Task Group E -- Developer Platform Tools --------------
    debug_console = providers.Singleton(
        _build_debug_console,
        event_bus=event_bus,
        settings=settings,
    )
    performance_profiler = providers.Singleton(
        _build_performance_profiler,
        event_bus=event_bus,
        settings=settings,
    )
    api_inspector = providers.Singleton(
        _build_api_inspector,
        settings=settings,
    )
    state_inspector = providers.Singleton(
        _build_state_inspector,
        service_manager=service_manager,
        plugin_registry=plugin_registry,
        runtime_manager=runtime_manager,
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
        knowledge=knowledge_service,
        intelligence=intelligence_service,
        event_bus=event_bus,
    )
