"""LangGraph tool bindings (Milestone 5-Agents).

One module per source service (``memory_tools``, ``automation_tools``,
``browser_tools``, ``system_tools``, ``voice_tools``, ``chat_tools``);
``registry.build_tool_registry`` assembles the final tool list handed to
the graph from whichever services are actually injected.
"""

from __future__ import annotations

from jarvis.agents.tools.registry import build_tool_registry

__all__ = ["build_tool_registry"]
