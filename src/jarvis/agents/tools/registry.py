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
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.system_service import SystemService
    from jarvis.services.vision_service import VisionService
    from jarvis.services.voice_service import VoiceService


def build_tool_registry(
    *,
    memory: MemoryService | None = None,
    automation: AutomationService | None = None,
    browser: BrowserService | None = None,
    system: SystemService | None = None,
    voice: VoiceService | None = None,
    chat: ChatService | None = None,
    vision: VisionService | None = None,
) -> list[BaseTool]:
    tools: list[BaseTool] = []

    if memory is not None:
        from jarvis.agents.tools.memory_tools import build_memory_tools

        tools += build_memory_tools(memory)
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
