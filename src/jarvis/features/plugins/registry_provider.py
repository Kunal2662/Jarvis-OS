"""Real ``IPluginProvider`` over the shipped Plugin Platform.

Replaces the Milestone 5-era ``MockPluginProvider``, which seeded two
invented plugins ("Weather Widget", "Spotify Connector") and a
three-entry invented marketplace because, when it was written, no
plugin loader existed. Milestone 9 Task Group C shipped one --
``core/plugins/`` has a real registry, loader, sandbox, permission
model, store and marketplace, and ``/api/v1/plugins/*`` already serves
them. The desktop Plugin Manager was simply never rewired, so it kept
rendering fabricated rows next to a working runtime.

That gap is what this closes: the same view, the same
``IPluginProvider`` port, reading the real registry. Nothing here
invents a plugin. An install with no plugins shows an empty state,
which is the honest answer.

**Why an adapter rather than teaching the view about the registry.**
``IPluginProvider`` is the port the view already consumes
(``core/interfaces/providers.py``), and the REST layer consumes the
same registry through its own thin adapter. Keeping the port means the
view is unchanged in shape, the layering rule holds (``ui`` never
reaches into ``core.plugins`` internals), and a future React Plugin
Manager reuses the REST route rather than this class.

**Install/uninstall/update are honestly unsupported here.**
``PluginRegistry`` implements all three, but each needs a *source
directory* -- a path the user chooses, or a package the store stages.
Picking that path is a file-dialog flow this backlog pass does not
ship, so these methods return ``False`` rather than guessing at a
source. The UI reflects that by disabling those buttons with a tooltip
that says why. Reporting "not wired here" is accurate; the capability
itself exists and is reachable over REST.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.core.plugins.marketplace import Marketplace
    from jarvis.core.plugins.registry import PluginRegistry

#: Registry states the Plugin Manager treats as "running". Everything
#: else (``disabled``, ``failed``, ``discovered``) is not enabled, so a
#: failed plugin never renders as if it were working.
_ENABLED_STATES = frozenset({"running"})

#: Registry state -> the badge vocabulary the view already understands.
#: ``failed`` deliberately maps to its own label rather than collapsing
#: into ``disabled``: a plugin that crashed on load and one the user
#: switched off are different situations, and the view has a warning
#: state for exactly this.
_STATE_LABELS = {
    "running": "enabled",
    "disabled": "disabled",
    "failed": "failed",
    "discovered": "discovered",
    "loading": "reloading",
    "stopping": "reloading",
}


class PluginRegistryProvider:
    """Implements ``core.interfaces.providers.IPluginProvider`` against
    the real :class:`~jarvis.core.plugins.registry.PluginRegistry`."""

    def __init__(self, registry: PluginRegistry, marketplace: Marketplace | None = None) -> None:
        self._registry = registry
        self._marketplace = marketplace

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def list_installed(self) -> list[dict[str, Any]]:
        """Every registered plugin, from the registry's own snapshot.

        The manifest supplies author and dependencies; the snapshot
        supplies live state. Where the manifest is missing a field, the
        value is reported as unknown rather than filled in with a
        plausible-looking default.
        """
        rows: list[dict[str, Any]] = []
        for snapshot in self._registry.snapshot():
            manifest = self._registry.get_manifest(snapshot.plugin_id)
            status = _STATE_LABELS.get(snapshot.state, snapshot.state)
            rows.append(
                {
                    "id": snapshot.plugin_id,
                    "name": snapshot.display_name or snapshot.plugin_id,
                    "version": snapshot.version or "unknown",
                    "author": _author_of(manifest),
                    "dependencies": list(manifest.dependencies) if manifest else [],
                    "permissions": list(snapshot.permissions),
                    "enabled": snapshot.state in _ENABLED_STATES,
                    "status": status,
                    "source": "installed",
                    # Surfaced so a failed plugin explains itself in the
                    # UI instead of showing a bare "failed" badge.
                    "error": snapshot.error,
                }
            )
        return rows

    async def list_marketplace(self) -> list[dict[str, Any]]:
        """The real marketplace index. Empty when no index is
        configured -- an empty catalogue is a true statement about this
        install, and inventing entries to fill the tab is what the
        previous implementation did wrong."""
        if self._marketplace is None:
            return []
        return [
            {
                "id": listing.plugin_id,
                "name": listing.display_name or listing.plugin_id,
                "version": listing.versions[-1] if listing.versions else "unknown",
                "author": listing.author or "unknown",
                "description": listing.description,
                "category": listing.category,
            }
            for listing in self._marketplace.browse()
        ]

    # ------------------------------------------------------------------
    # Lifecycle -- these are genuinely wired
    # ------------------------------------------------------------------
    async def enable(self, plugin_id: str) -> bool:
        return await self._registry.enable(plugin_id)

    async def disable(self, plugin_id: str) -> bool:
        return await self._registry.disable(plugin_id)

    async def reload(self, plugin_id: str) -> bool:
        """Stop then start, through the registry's own transitions --
        not a second reload path with its own idea of plugin state.

        ``disable`` returning ``False`` means the plugin was not running
        (already disabled, or failed), in which case enabling it is
        still the right thing to attempt and is what the user asked
        for by pressing Reload.
        """
        await self._registry.disable(plugin_id)
        return await self._registry.enable(plugin_id)

    # ------------------------------------------------------------------
    # Not wired from this surface -- see the module docstring
    # ------------------------------------------------------------------
    async def install(self, plugin_id: str) -> bool:
        return False

    async def uninstall(self, plugin_id: str) -> bool:
        return False

    async def update(self, plugin_id: str) -> bool:
        return False


def _author_of(manifest: Any) -> str:
    """Author lives under ``developer_metadata``; a manifest may omit
    it entirely, and "unknown" is the honest rendering."""
    if manifest is None:
        return "unknown"
    metadata = getattr(manifest, "developer_metadata", None)
    return getattr(metadata, "author", "") or "unknown"
