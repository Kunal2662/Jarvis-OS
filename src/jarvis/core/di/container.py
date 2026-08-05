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
    workspace_service: Any,
    task_service: Any,
    calendar_service: Any,
    reminder_service: Any,
    file_service: Any,
    folder_service: Any,
    attachment_service: Any,
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
        AttachmentSearchSource,
        CalendarSearchSource,
        CommandSearchSource,
        FileSearchSource,
        FolderSearchSource,
        GoalSearchSource,
        KnowledgeSearchSource,
        MemorySearchSource,
        NoteSearchSource,
        ProjectSearchSource,
        ReminderSearchSource,
        TaskSearchSource,
        WorkspaceSearchSource,
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
    # Milestone 11 Task Group A -- three more sources, registered the
    # same way, with no change to SearchService itself. That is the
    # extensibility M10A's provider registry was built for.
    service.register_source(WorkspaceSearchSource(workspace_service))
    service.register_source(ProjectSearchSource(workspace_service))
    service.register_source(NoteSearchSource(workspace_service))
    # Milestone 11 Task Group B -- three more, same registry, still
    # no change to SearchService itself.
    service.register_source(TaskSearchSource(task_service))
    service.register_source(CalendarSearchSource(calendar_service))
    service.register_source(ReminderSearchSource(reminder_service))
    # Milestone 11 Task Group C -- three more, same registry, still no
    # change to SearchService. `files` is the first source whose corpus
    # includes extracted document text rather than only stored fields.
    service.register_source(FileSearchSource(file_service))
    service.register_source(FolderSearchSource(folder_service))
    service.register_source(AttachmentSearchSource(attachment_service))
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


def _build_mcp_transport_registry(*, mcp_server_runtime: Any) -> Any:
    """Every shipped transport, registered (M10.5 Task Group B).

    Task Group A left this registry deliberately empty and documented
    that a later pass would populate it at the DI composition root --
    this is that call. Passing the server runtime also registers the
    ``in_process`` transport, so JARVIS's own MCP server is reachable
    through the same factory as any remote peer.
    """
    from jarvis.core.mcp.transports.factory import build_default_transport_registry

    return build_default_transport_registry(in_process_server=mcp_server_runtime)


def _build_mcp_credential_store(*, settings: Settings) -> Any:
    """Reuses the existing config-dir convention and the app's own
    Fernet key -- no second crypto stack, no new location."""
    from jarvis.core.config import paths as _paths
    from jarvis.core.mcp.auth.store import CredentialStore

    return CredentialStore(
        _paths.config_dir(settings.resolved_data_dir) / "mcp_credentials.json",
        secret_key=settings.security.secret_key.get_secret_value(),
    )


def _build_mcp_auth_strategies() -> Any:
    from jarvis.core.mcp.auth.strategies import build_default_strategy_registry

    return build_default_strategy_registry()


def _build_mcp_auth_manager(
    *,
    mcp_credential_store: Any,
    mcp_auth_strategies: Any,
    permission_model: Any,
    event_bus: Any,
) -> Any:
    from jarvis.core.mcp.auth.manager import MCPAuthManager

    return MCPAuthManager(
        mcp_credential_store,
        mcp_auth_strategies,
        permission_model,
        event_bus=event_bus,
    )


def _build_workspace_service(*, database: Any, event_bus: Any) -> Any:
    from jarvis.services.workspace_service import WorkspaceService

    return WorkspaceService(database=database, event_bus=event_bus)


def _build_workspace_manager(
    *,
    workspace_service: Any,
    knowledge_service: Any,
    search_service: Any,
    memory_service: Any,
    workspace_knowledge_service: Any,
) -> Any:
    """Milestone 11 Task Group A. Composed here, at the composition
    root, rather than inside ``WorkspaceService`` -- see
    ``services/workspace_manager.py`` for why the service stays
    single-subsystem. Task Group D adds the link store, so
    ``context()`` can report what a workspace's text actually produced
    alongside what merely shares words with it."""
    from jarvis.services.workspace_manager import WorkspaceManager

    return WorkspaceManager(
        workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
        knowledge_links=workspace_knowledge_service,
    )


def _build_task_service(*, database: Any, workspace_service: Any, event_bus: Any) -> Any:
    from jarvis.services.task_service import TaskService

    return TaskService(database=database, workspace_service=workspace_service, event_bus=event_bus)


def _build_calendar_service(*, database: Any, workspace_service: Any, event_bus: Any) -> Any:
    from jarvis.services.calendar_service import CalendarService

    return CalendarService(
        database=database, workspace_service=workspace_service, event_bus=event_bus
    )


def _build_reminder_service(*, database: Any, workspace_service: Any, event_bus: Any) -> Any:
    from jarvis.services.reminder_service import ReminderService

    return ReminderService(
        database=database, workspace_service=workspace_service, event_bus=event_bus
    )


def _build_task_manager(
    *,
    task_service: Any,
    workspace_service: Any,
    knowledge_service: Any,
    search_service: Any,
    memory_service: Any,
) -> Any:
    """Milestone 11 Task Group B. Composed at the composition root, like
    ``workspace_manager`` -- the service stays single-subsystem."""
    from jarvis.services.productivity_managers import TaskManager

    return TaskManager(
        task_service,
        workspace_service=workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
    )


def _build_calendar_manager(
    *,
    calendar_service: Any,
    workspace_service: Any,
    knowledge_service: Any,
    search_service: Any,
    memory_service: Any,
) -> Any:
    from jarvis.services.productivity_managers import CalendarManager

    return CalendarManager(
        calendar_service,
        workspace_service=workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
    )


def _build_reminder_manager(
    *,
    reminder_service: Any,
    task_service: Any,
    calendar_service: Any,
    workspace_service: Any,
    search_service: Any,
) -> Any:
    from jarvis.services.productivity_managers import ReminderManager

    return ReminderManager(
        reminder_service,
        task_service=task_service,
        calendar_service=calendar_service,
        workspace_service=workspace_service,
        search_service=search_service,
    )


def _build_folder_service(*, database: Any, settings: Settings, event_bus: Any) -> Any:
    """Milestone 11 Task Group C. The storage root is resolved here, at
    the composition root, and handed to the service as a plain ``Path``
    -- so the service depends on a directory rather than on the whole
    settings object, and a test can point it at a temporary one without
    constructing a ``Settings``."""
    from jarvis.services.file_service import FolderService

    return FolderService(
        database=database,
        storage_root=settings.resolved_files_dir,
        event_bus=event_bus,
    )


def _build_file_service(*, database: Any, settings: Settings, event_bus: Any) -> Any:
    from jarvis.services.file_service import FileService

    return FileService(
        database=database,
        storage_root=settings.resolved_files_dir,
        event_bus=event_bus,
        index_enabled=settings.files.index_enabled,
        index_max_bytes=settings.files.index_max_bytes,
    )


def _build_attachment_service(*, database: Any, event_bus: Any) -> Any:
    """No storage root: an attachment links two rows that already
    exist, so this service never touches disk."""
    from jarvis.services.file_service import AttachmentService

    return AttachmentService(database=database, event_bus=event_bus)


def _build_folder_manager(
    *,
    folder_service: Any,
    file_service: Any,
    workspace_service: Any,
    search_service: Any,
) -> Any:
    from jarvis.services.file_managers import FolderManager

    return FolderManager(
        folder_service,
        file_service=file_service,
        workspace_service=workspace_service,
        search_service=search_service,
    )


def _build_file_manager(
    *,
    file_service: Any,
    folder_service: Any,
    attachment_service: Any,
    workspace_service: Any,
    knowledge_service: Any,
    search_service: Any,
    memory_service: Any,
) -> Any:
    from jarvis.services.file_managers import FileManager

    return FileManager(
        file_service,
        folder_service=folder_service,
        attachment_service=attachment_service,
        workspace_service=workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
    )


def _build_attachment_manager(
    *,
    attachment_service: Any,
    file_service: Any,
    workspace_service: Any,
    search_service: Any,
) -> Any:
    from jarvis.services.file_managers import AttachmentManager

    return AttachmentManager(
        attachment_service,
        file_service=file_service,
        workspace_service=workspace_service,
        search_service=search_service,
    )


def _build_workspace_knowledge_service(
    *,
    database: Any,
    knowledge_service: Any,
    workspace_service: Any,
    file_service: Any,
    event_bus: Any,
) -> Any:
    """Milestone 11 Task Group D. ``knowledge_service`` is a constructor
    argument rather than an optional collaborator because this service
    *is* the bridge between the workspace domain and the graph -- see
    ``services/workspace_ai_service.py``."""
    from jarvis.services.workspace_ai_service import WorkspaceKnowledgeService

    return WorkspaceKnowledgeService(
        database=database,
        knowledge_service=knowledge_service,
        workspace_service=workspace_service,
        file_service=file_service,
        event_bus=event_bus,
    )


def _build_workspace_context_manager(
    *,
    settings: Settings,
    workspace_service: Any,
    task_manager: Any,
    task_service: Any,
    calendar_manager: Any,
    reminder_manager: Any,
    file_manager: Any,
    workspace_knowledge_service: Any,
    knowledge_service: Any,
    memory_service: Any,
) -> Any:
    """Composed at the composition root out of the *managers* each
    subsystem already owns, not their services -- reaching past
    ``TaskManager`` to recompute what is overdue would be a second
    implementation of the arithmetic that manager exists to own.
    ``task_service`` is the single exception, and only for the plain
    listing of open tasks no manager exposes; the urgency judgement
    still comes from ``TaskManager.agenda``."""
    from jarvis.services.workspace_ai_managers import WorkspaceContextManager

    return WorkspaceContextManager(
        workspace_service,
        task_manager=task_manager,
        task_service=task_service,
        calendar_manager=calendar_manager,
        reminder_manager=reminder_manager,
        file_manager=file_manager,
        knowledge_links=workspace_knowledge_service,
        knowledge_service=knowledge_service,
        memory_service=memory_service,
        budget_chars=settings.ai_workspace.context_budget_chars,
        section_items=settings.ai_workspace.context_section_items,
        item_chars=settings.ai_workspace.context_item_chars,
    )


def _build_workspace_retriever(
    *,
    settings: Settings,
    workspace_service: Any,
    search_service: Any,
    calendar_service: Any,
    task_service: Any,
    file_service: Any,
) -> Any:
    from jarvis.services.workspace_ai_managers import WorkspaceRetriever

    return WorkspaceRetriever(
        workspace_service,
        search_service=search_service,
        calendar_service=calendar_service,
        task_service=task_service,
        file_service=file_service,
        overfetch=settings.ai_workspace.retrieval_overfetch,
    )


def _build_workspace_assistant_service(
    *,
    settings: Settings,
    llm: Any,
    workspace_context_manager: Any,
    workspace_retriever: Any,
    workspace_service: Any,
    event_bus: Any,
) -> Any:
    from jarvis.services.workspace_ai_service import WorkspaceAssistantService

    return WorkspaceAssistantService(
        llm=llm,
        context_manager=workspace_context_manager,
        retriever=workspace_retriever,
        workspace_service=workspace_service,
        event_bus=event_bus,
        default_top_k=settings.ai_workspace.retrieval_top_k,
    )


def _build_health_monitor(*, service_manager: Any, event_bus: Any, settings: Settings) -> Any:
    """Points the disk metrics at the data directory -- the volume
    JARVIS can actually fill, and therefore the one worth budgeting."""
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    return HealthMonitor(
        service_manager,
        event_bus,
        disk_path=str(settings.resolved_data_dir),
    )


def _build_mcp_diagnostics(
    *,
    mcp_server_runtime: Any,
    mcp_client_runtime: Any,
    mcp_transport_registry: Any,
    mcp_provider_manager: Any,
    mcp_auth_manager: Any,
    mcp_auth_strategies: Any,
    mcp_heartbeat_monitor: Any,
) -> Any:
    """Read-only aggregator over every MCP subsystem (M10.5 Task Group E).
    Reads the same singletons the REST API does, so the CLI and the API
    can never report a different truth."""
    from jarvis.core.mcp.diagnostics import MCPDiagnostics

    return MCPDiagnostics(
        server=mcp_server_runtime,
        client=mcp_client_runtime,
        transports=mcp_transport_registry,
        provider_manager=mcp_provider_manager,
        auth_manager=mcp_auth_manager,
        auth_strategies=mcp_auth_strategies,
        heartbeat=mcp_heartbeat_monitor,
    )


def _build_mcp_provider_registry() -> Any:
    from jarvis.core.mcp.providers.registry import MCPProviderRegistry

    return MCPProviderRegistry()


def _build_mcp_provider_manager(
    *,
    mcp_provider_registry: Any,
    mcp_client_runtime: Any,
    mcp_transport_registry: Any,
    permission_model: Any,
    event_bus: Any,
) -> Any:
    from jarvis.core.mcp.providers.manager import MCPProviderManager

    return MCPProviderManager(
        mcp_provider_registry,
        client_runtime=mcp_client_runtime,
        transport_registry=mcp_transport_registry,
        permission_model=permission_model,
        event_bus=event_bus,
    )


def _build_mcp_heartbeat_monitor(
    *, mcp_client_runtime: Any, event_bus: Any, settings: Settings
) -> Any:
    from jarvis.core.mcp.heartbeat import MCPHeartbeatMonitor

    return MCPHeartbeatMonitor(
        mcp_client_runtime,
        event_bus=event_bus,
        interval_seconds=settings.mcp.heartbeat_interval_seconds,
    )


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
    workspace_assistant: Any,
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
        workspace_assistant=workspace_assistant,
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
    # ---- Milestone 11 Task Group A -- Workspace Foundation ----------------
    workspace_service = providers.Singleton(
        _build_workspace_service,
        database=database,
        event_bus=event_bus,
    )

    # ---- Milestone 11 Task Group B -- Productivity Core -------------------
    task_service = providers.Singleton(
        _build_task_service,
        database=database,
        workspace_service=workspace_service,
        event_bus=event_bus,
    )
    calendar_service = providers.Singleton(
        _build_calendar_service,
        database=database,
        workspace_service=workspace_service,
        event_bus=event_bus,
    )
    reminder_service = providers.Singleton(
        _build_reminder_service,
        database=database,
        workspace_service=workspace_service,
        event_bus=event_bus,
    )

    # ---- Milestone 11 Task Group C -- File Platform -----------------------
    folder_service = providers.Singleton(
        _build_folder_service,
        database=database,
        settings=settings,
        event_bus=event_bus,
    )
    file_service = providers.Singleton(
        _build_file_service,
        database=database,
        settings=settings,
        event_bus=event_bus,
    )
    attachment_service = providers.Singleton(
        _build_attachment_service,
        database=database,
        event_bus=event_bus,
    )

    # ---- Milestone 11 Task Group D -- AI Workspace (link store) -----------
    # Declared with the services rather than with the rest of Task Group
    # D further down, because `workspace_manager` (M11 Task Group A)
    # composes it and a provider can only reference names already bound
    # in this class body. Its own dependencies are all services above it.
    workspace_knowledge_service = providers.Singleton(
        _build_workspace_knowledge_service,
        database=database,
        knowledge_service=knowledge_service,
        workspace_service=workspace_service,
        file_service=file_service,
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
        _build_health_monitor,
        service_manager=service_manager,
        event_bus=event_bus,
        settings=settings,
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
    # ---- Milestone 10.5 Task Group B -- Transport Layer -------------------
    mcp_transport_registry = providers.Singleton(
        _build_mcp_transport_registry,
        mcp_server_runtime=mcp_server_runtime,
    )
    mcp_heartbeat_monitor = providers.Singleton(
        _build_mcp_heartbeat_monitor,
        mcp_client_runtime=mcp_client_runtime,
        event_bus=event_bus,
        settings=settings,
    )
    # ---- Milestone 10.5 Task Group D -- Authentication --------------------
    mcp_credential_store = providers.Singleton(
        _build_mcp_credential_store,
        settings=settings,
    )
    mcp_auth_strategies = providers.Singleton(_build_mcp_auth_strategies)
    mcp_auth_manager = providers.Singleton(
        _build_mcp_auth_manager,
        mcp_credential_store=mcp_credential_store,
        mcp_auth_strategies=mcp_auth_strategies,
        permission_model=permission_model,
        event_bus=event_bus,
    )

    # ---- Milestone 10.5 Task Group C -- Provider Framework ----------------
    mcp_provider_registry = providers.Singleton(_build_mcp_provider_registry)
    mcp_provider_manager = providers.Singleton(
        _build_mcp_provider_manager,
        mcp_provider_registry=mcp_provider_registry,
        mcp_client_runtime=mcp_client_runtime,
        mcp_transport_registry=mcp_transport_registry,
        permission_model=permission_model,
        event_bus=event_bus,
    )

    # ---- Milestone 10.5 Task Group E -- SDK & Developer Experience --------
    mcp_diagnostics = providers.Singleton(
        _build_mcp_diagnostics,
        mcp_server_runtime=mcp_server_runtime,
        mcp_client_runtime=mcp_client_runtime,
        mcp_transport_registry=mcp_transport_registry,
        mcp_provider_manager=mcp_provider_manager,
        mcp_auth_manager=mcp_auth_manager,
        mcp_auth_strategies=mcp_auth_strategies,
        mcp_heartbeat_monitor=mcp_heartbeat_monitor,
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
        workspace_service=workspace_service,
        task_service=task_service,
        calendar_service=calendar_service,
        reminder_service=reminder_service,
        file_service=file_service,
        folder_service=folder_service,
        attachment_service=attachment_service,
    )

    # Declared after `search_service` because it composes it -- the
    # manager is the read-side coordinator, not a second search path.
    workspace_manager = providers.Singleton(
        _build_workspace_manager,
        workspace_service=workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
        workspace_knowledge_service=workspace_knowledge_service,
    )

    # Declared after `search_service` for the same reason
    # `workspace_manager` is: each composes it rather than duplicating a
    # second ranking path.
    task_manager = providers.Singleton(
        _build_task_manager,
        task_service=task_service,
        workspace_service=workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
    )
    calendar_manager = providers.Singleton(
        _build_calendar_manager,
        calendar_service=calendar_service,
        workspace_service=workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
    )
    reminder_manager = providers.Singleton(
        _build_reminder_manager,
        reminder_service=reminder_service,
        task_service=task_service,
        calendar_service=calendar_service,
        workspace_service=workspace_service,
        search_service=search_service,
    )

    # Milestone 11 Task Group C, declared here for the same reason.
    folder_manager = providers.Singleton(
        _build_folder_manager,
        folder_service=folder_service,
        file_service=file_service,
        workspace_service=workspace_service,
        search_service=search_service,
    )
    file_manager = providers.Singleton(
        _build_file_manager,
        file_service=file_service,
        folder_service=folder_service,
        attachment_service=attachment_service,
        workspace_service=workspace_service,
        knowledge_service=knowledge_service,
        search_service=search_service,
        memory_service=memory_service,
    )
    attachment_manager = providers.Singleton(
        _build_attachment_manager,
        attachment_service=attachment_service,
        file_service=file_service,
        workspace_service=workspace_service,
        search_service=search_service,
    )

    # ---- Milestone 11 Task Group D -- composed AI Workspace ---------------
    # The rest of Task Group D, declared here rather than beside
    # `workspace_knowledge_service` above because these three compose
    # every subsystem before them: the context manager reads through
    # Task Group B and C's *managers*, and the retriever narrows the
    # shared `search_service` rather than standing up an index of its own.
    workspace_context_manager = providers.Singleton(
        _build_workspace_context_manager,
        settings=settings,
        workspace_service=workspace_service,
        task_manager=task_manager,
        task_service=task_service,
        calendar_manager=calendar_manager,
        reminder_manager=reminder_manager,
        file_manager=file_manager,
        workspace_knowledge_service=workspace_knowledge_service,
        knowledge_service=knowledge_service,
        memory_service=memory_service,
    )
    workspace_retriever = providers.Singleton(
        _build_workspace_retriever,
        settings=settings,
        workspace_service=workspace_service,
        search_service=search_service,
        calendar_service=calendar_service,
        task_service=task_service,
        file_service=file_service,
    )
    workspace_assistant_service = providers.Singleton(
        _build_workspace_assistant_service,
        settings=settings,
        llm=llm_provider,
        workspace_context_manager=workspace_context_manager,
        workspace_retriever=workspace_retriever,
        workspace_service=workspace_service,
        event_bus=event_bus,
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
        # M10B's Goal Manager, so the greeting's "work context" is the
        # user's real open and completed goals rather than invented ones.
        intelligence_service=intelligence_service,
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
        workspace_assistant=workspace_assistant_service,
        event_bus=event_bus,
    )
