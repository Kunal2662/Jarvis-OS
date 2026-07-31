"""Mock plugin provider (Milestone 5, section 7) implementing
``IPluginProvider`` (section 11).

There is still no real third-party plugin loader -- that's genuine
future work, not something to fake. What this *does* provide is the
full architecture the brief asks for ("prepare architecture only"):
installed-plugin metadata (version, author, dependencies, permissions),
enable/disable/reload against a mock in-memory store, a marketplace
placeholder list, and install/uninstall/update methods that exist on
the interface but are honestly not wired to anything real yet.

Real, on-disk plugin folders under ``<data_dir>/plugins/`` are still
picked up and shown (same honesty as the original view) -- they just
get enriched with mock metadata since a real plugin manifest format
doesn't exist yet either.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class MockPluginProvider:
    """Implements ``core.interfaces.providers.IPluginProvider``."""

    def __init__(self, plugins_dir: Path) -> None:
        self._plugins_dir = plugins_dir
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._installed: dict[str, dict[str, Any]] = self._seed()

    def _seed(self) -> dict[str, dict[str, Any]]:
        # Real on-disk folders (if any) get honest placeholder metadata;
        # plus two illustrative mock entries so the UI has something
        # real to render even on a fresh install.
        discovered = {
            p.name: {
                "id": p.name,
                "name": p.name,
                "version": "unknown",
                "author": "unknown",
                "dependencies": [],
                "permissions": [],
                "enabled": False,
                "status": "disabled",
                "source": "local folder",
            }
            for p in self._plugins_dir.iterdir()
            if p.is_dir()
        }
        mock_examples = {
            "weather-widget": {
                "id": "weather-widget",
                "name": "Weather Widget",
                "version": "1.2.0",
                "author": "JARVIS Team",
                "dependencies": [],
                "permissions": ["network"],
                "enabled": True,
                "status": "enabled",
                "source": "built-in example",
            },
            "spotify-connector": {
                "id": "spotify-connector",
                "name": "Spotify Connector",
                "version": "0.8.1",
                "author": "Community",
                "dependencies": ["weather-widget"],
                "permissions": ["network", "media"],
                "enabled": False,
                "status": "disabled",
                "source": "built-in example",
            },
        }
        return {**mock_examples, **discovered}

    async def list_installed(self) -> list[dict[str, Any]]:
        await asyncio.sleep(0.02)
        return list(self._installed.values())

    async def list_marketplace(self) -> list[dict[str, Any]]:
        await asyncio.sleep(0.02)
        # Placeholder catalog -- no real marketplace backend exists yet.
        return [
            {
                "id": "finance-tracker",
                "name": "Finance Tracker",
                "version": "2.0.0",
                "author": "Community",
            },
            {
                "id": "smart-home-hub",
                "name": "Smart Home Hub",
                "version": "1.5.0",
                "author": "JARVIS Team",
            },
            {
                "id": "code-reviewer",
                "name": "Code Reviewer",
                "version": "0.3.0",
                "author": "Community",
            },
        ]

    async def enable(self, plugin_id: str) -> bool:
        await asyncio.sleep(0.05)
        plugin = self._installed.get(plugin_id)
        if plugin is None:
            return False
        plugin["enabled"] = True
        plugin["status"] = "enabled"
        return True

    async def disable(self, plugin_id: str) -> bool:
        await asyncio.sleep(0.05)
        plugin = self._installed.get(plugin_id)
        if plugin is None:
            return False
        plugin["enabled"] = False
        plugin["status"] = "disabled"
        return True

    async def reload(self, plugin_id: str) -> bool:
        plugin = self._installed.get(plugin_id)
        if plugin is None:
            return False
        plugin["status"] = "reloading"
        await asyncio.sleep(0.1)
        plugin["status"] = "enabled" if plugin["enabled"] else "disabled"
        return True

    async def install(self, plugin_id: str) -> bool:
        # Future -- not wired yet; no loader exists to actually install into.
        await asyncio.sleep(0.02)
        return False

    async def uninstall(self, plugin_id: str) -> bool:
        # Future -- not wired yet.
        await asyncio.sleep(0.02)
        return False

    async def update(self, plugin_id: str) -> bool:
        # Future -- not wired yet.
        await asyncio.sleep(0.02)
        return False
