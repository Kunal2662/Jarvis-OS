"""Smoke test that the package imports and its architecture is intact."""

from __future__ import annotations


def test_package_version_exported() -> None:
    import jarvis

    assert isinstance(jarvis.__version__, str)
    assert jarvis.__version__


def test_core_interfaces_public_surface() -> None:
    from jarvis.core.interfaces import (
        IAgentOrchestrator,
        IBrowserAutomation,
        IDatabase,
        ILLMProvider,
        IOSAutomation,
        ISTTProvider,
        ITTSProvider,
        IVectorStore,
    )

    for iface in (
        IAgentOrchestrator,
        IBrowserAutomation,
        IDatabase,
        ILLMProvider,
        IOSAutomation,
        ISTTProvider,
        ITTSProvider,
        IVectorStore,
    ):
        assert iface is not None


def test_di_container_declares_all_providers() -> None:
    from jarvis.core.di.container import Container

    for name in (
        "settings",
        "event_bus",
        "llm_provider",
        "stt_provider",
        "tts_provider",
        "vector_store",
        "database",
        "browser",
        "os_automation",
        "chat_service",
        "voice_service",
        "memory_service",
        "conversation_service",
        "automation_service",
        "browser_service",
        "system_service",
        "settings_service",
        "theme_service",
        "agent_orchestrator",
        "api_center_service",
        "developer_mode_service",
        "voice_announcement_service",
        "update_service",
        "greeting_service",
        "runtime_manager",
    ):
        assert hasattr(Container, name), f"DI container missing provider: {name}"
