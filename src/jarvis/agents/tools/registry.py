"""Assembles the full agent tool list from whichever services are injected.

Every service the roadmap names (``ChatService``, ``VoiceService``,
``MemoryService``, ``AutomationService``, ``BrowserService``,
``SystemService``) is optional here on purpose: ``AgentOrchestrator``'s
constructor keeps ``memory``/``automation``/``browser`` required (its
pre-existing signature) and ``chat``/``voice``/``system`` optional, so
tests and future call sites can build a narrower agent without wiring
every service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from jarvis.services.automation_service import AutomationService
    from jarvis.services.browser_service import BrowserService
    from jarvis.services.chat_service import ChatService
    from jarvis.services.integration_service import IntegrationService
    from jarvis.services.intelligence_service import IntelligenceService
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.system_service import SystemService
    from jarvis.services.vision_service import VisionService
    from jarvis.services.voice_service import VoiceService
    from jarvis.services.workspace_ai_service import WorkspaceAssistantService


def build_tool_registry(
    *,
    memory: MemoryService | None = None,
    automation: AutomationService | None = None,
    browser: BrowserService | None = None,
    system: SystemService | None = None,
    voice: VoiceService | None = None,
    chat: ChatService | None = None,
    vision: VisionService | None = None,
    knowledge: KnowledgeService | None = None,
    intelligence: IntelligenceService | None = None,
    workspace_assistant: WorkspaceAssistantService | None = None,
    integrations: IntegrationService | None = None,
) -> list[BaseTool]:
    tools: list[BaseTool] = []

    if memory is not None:
        from jarvis.agents.tools.memory_tools import build_memory_tools

        tools += build_memory_tools(memory)
    if knowledge is not None:
        from jarvis.agents.tools.knowledge_tools import build_knowledge_tools

        tools += build_knowledge_tools(knowledge)
    if intelligence is not None:
        from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

        tools += build_intelligence_tools(intelligence)
    if workspace_assistant is not None:
        # Milestone 11 Task Group D. Optional like every other service
        # here, and deliberately *not* passed by `_build_search_service`'s
        # own `build_tool_registry` call: the assistant composes
        # `SearchService`, so resolving it there would close a cycle at
        # the composition root.
        from jarvis.agents.tools.workspace_tools import build_workspace_tools

        tools += build_workspace_tools(workspace_assistant)
    if integrations is not None:
        # Milestone 11 Task Group E. Four discovery-and-invoke tools
        # rather than one per vendor operation -- see
        # `agents/tools/integration_tools.py` for why the catalogue does
        # not belong on the tool-selection prompt.
        from jarvis.agents.tools.integration_tools import build_integration_tools

        tools += build_integration_tools(integrations)
    if automation is not None:
        from jarvis.agents.tools.automation_tools import build_automation_tools

        tools += build_automation_tools(automation)
    if browser is not None:
        from jarvis.agents.tools.browser_tools import build_browser_tools

        tools += build_browser_tools(browser)
    if system is not None:
        from jarvis.agents.tools.system_tools import build_system_tools

        tools += build_system_tools(system)
    if voice is not None:
        from jarvis.agents.tools.voice_tools import build_voice_tools

        tools += build_voice_tools(voice)
    if chat is not None:
        from jarvis.agents.tools.chat_tools import build_chat_tools

        tools += build_chat_tools(chat)
    if vision is not None:
        from jarvis.agents.tools.vision_tools import build_vision_tools

        tools += build_vision_tools(vision)

    return tools
