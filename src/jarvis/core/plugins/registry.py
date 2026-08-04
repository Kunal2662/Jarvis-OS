"""Plugin Registration System -- Milestone 9 Task Group D, Phase 6.

``PluginRegistry`` is the top-level facade composing every earlier
phase -- Loader (discovery, import, compatibility), Sandbox (isolated
hook execution), Extension API (the context handed to ``on_load``),
Permission Model (declare-on-register, gate-on-check) -- into the one
object the rest of the application talks to, the same "registry of
real components, dependency-ordered, fault-isolated" shape
``core/lifecycle/service_manager.py``'s ``ServiceManager`` already
established for first-party services.

**Fault isolation, concretely.** ``discover_and_load_all`` never lets
one plugin's failure stop another's: a compatibility rejection, an
``on_load``/``on_start`` exception (already isolated by the Sandbox,
Phase 3, into a reported :class:`~jarvis.core.plugins.sandbox.
SandboxResult` rather than a raised exception), or a missing/circular
dependency (already isolated by the Loader, Phase 2, into
``LoadOrderResult.unresolved``) all land as this one plugin's own
``FAILED`` state, never an exception propagating out of the batch.

**Install/uninstall/update work on an already-trusted local
directory.** This phase does not fetch or verify a package from
anywhere -- that is Phase 7 (Plugin Store)'s job, which stages a
package down to a local, verified directory and then calls
:meth:`PluginRegistry.install` with it. Keeping "is this plugin's code
in a form I can safely load" (Phase 7) separate from "manage this
already-trusted plugin's registered lifecycle" (this phase) mirrors
Phase 2/3's own "import" vs "run" split.
"""

from __future__ import annotations

import enum
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import (
    PluginDisabledEvent,
    PluginDiscoveredEvent,
    PluginEnabledEvent,
    PluginInstalledEvent,
    PluginLoadedEvent,
    PluginLoadFailedEvent,
    PluginUninstalledEvent,
    PluginUnloadedEvent,
    PluginUpdatedEvent,
)
from jarvis.core.interfaces.service import HealthStatus, ServiceStatus
from jarvis.core.logging.logger import get_logger
from jarvis.core.plugins.extension_api import PluginContext, build_plugin_context
from jarvis.core.plugins.loader import DiscoveredPlugin, PluginLoadError
from jarvis.core.plugins.manifest import PluginManifestError, load_manifest
from jarvis.core.plugins.sdk import PluginError

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.platform import IPlatformAdapter
    from jarvis.core.plugins.loader import PluginLoader
    from jarvis.core.plugins.manifest import PluginManifest
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.core.plugins.sandbox import PluginSandbox

_logger = get_logger("jarvis.core.plugins.registry")


class PluginRegistryError(PluginError):
    """Raised for a specific plugin's own registry-level operation
    failure (install/uninstall/update) -- never for a different
    plugin's problem."""


class PluginState(enum.StrEnum):
    DISCOVERED = "discovered"
    LOADING = "loading"
    RUNNING = "running"
    STOPPING = "stopping"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass(slots=True)
class _Entry:
    plugin_id: str
    manifest: PluginManifest
    discovered: DiscoveredPlugin
    state: PluginState = PluginState.DISCOVERED
    error: str = ""
    context: PluginContext | None = None
    instance: Any = None


@dataclass(frozen=True, slots=True)
class PluginSnapshot:
    plugin_id: str
    display_name: str
    version: str
    state: str
    error: str = ""
    permissions: tuple[str, ...] = field(default_factory=tuple)


class PluginRegistry:
    def __init__(
        self,
        *,
        loader: PluginLoader,
        sandbox: PluginSandbox,
        permission_model: PermissionModel,
        event_bus: EventBus,
        platform_adapter: IPlatformAdapter,
        plugin_data_root: Path,
        hotkey_service: Any | None = None,
    ) -> None:
        self._loader = loader
        self._sandbox = sandbox
        self._permission_model = permission_model
        self._event_bus = event_bus
        self._platform_adapter = platform_adapter
        self._plugin_data_root = plugin_data_root
        self._hotkey_service = hotkey_service
        self._entries: dict[str, _Entry] = {}

    # ---- Bulk startup -----------------------------------------------------
    async def discover_and_load_all(self) -> None:
        """Real orchestration: discover -> resolve dependency order ->
        load each in order. Never raises -- every failure is isolated
        to its own plugin's ``FAILED`` state."""
        discovered = self._loader.discover()
        for plugin in discovered:
            self._entries[plugin.plugin_id] = _Entry(
                plugin_id=plugin.plugin_id, manifest=plugin.manifest, discovered=plugin
            )
            await self._event_bus.publish(PluginDiscoveredEvent(plugin_id=plugin.plugin_id))

        order_result = self._loader.resolve_load_order(discovered)
        for plugin_id, reason in order_result.unresolved.items():
            await self._mark_failed(plugin_id, reason)
        for plugin_id in order_result.order:
            await self.load_one(plugin_id)

    async def stop_all(self) -> None:
        """Reverse of :meth:`discover_and_load_all` -- disables every
        currently-``RUNNING`` plugin. Same fault isolation: one
        plugin's ``on_stop`` failing never blocks the rest."""
        for plugin_id in [
            pid for pid, e in self._entries.items() if e.state is PluginState.RUNNING
        ]:
            await self.disable(plugin_id)

    # ---- Single-plugin load/unload -----------------------------------------
    async def load_one(self, plugin_id: str) -> bool:
        entry = self._entries.get(plugin_id)
        if entry is None:
            raise PluginRegistryError(f"Plugin {plugin_id!r} is not registered.")

        entry.state = PluginState.LOADING
        self._permission_model.declare(plugin_id, entry.manifest.permissions)

        try:
            instance = self._loader.import_plugin(entry.discovered)
        except PluginLoadError as err:
            await self._mark_failed(plugin_id, str(err))
            return False

        context = build_plugin_context(
            entry.manifest,
            event_bus=self._event_bus,
            permission_checker=self._permission_model,
            platform_adapter=self._platform_adapter,
            data_dir=self._plugin_data_root / plugin_id,
            hotkey_service=self._hotkey_service,
        )

        load_result = await self._sandbox.run_hook(plugin_id, instance, "on_load", context)
        if not load_result.succeeded:
            await self._mark_failed(plugin_id, load_result.error)
            return False

        start_result = await self._sandbox.run_hook(plugin_id, instance, "on_start")
        if not start_result.succeeded:
            await self._mark_failed(plugin_id, start_result.error)
            return False

        entry.instance = instance
        entry.context = context
        entry.state = PluginState.RUNNING
        entry.error = ""
        await self._event_bus.publish(PluginLoadedEvent(plugin_id=plugin_id))
        return True

    async def disable(self, plugin_id: str) -> bool:
        entry = self._entries.get(plugin_id)
        if entry is None or entry.state is not PluginState.RUNNING:
            return False
        entry.state = PluginState.STOPPING
        if entry.instance is not None:
            await self._sandbox.run_hook(plugin_id, entry.instance, "on_stop")
        if entry.context is not None:
            entry.context.hotkeys.unregister_all()
        self._loader.unload(plugin_id)
        entry.instance = None
        entry.context = None
        entry.state = PluginState.DISABLED
        await self._event_bus.publish(PluginUnloadedEvent(plugin_id=plugin_id))
        await self._event_bus.publish(PluginDisabledEvent(plugin_id=plugin_id))
        return True

    async def enable(self, plugin_id: str) -> bool:
        entry = self._entries.get(plugin_id)
        if entry is None or entry.state not in (PluginState.DISABLED, PluginState.FAILED):
            return False
        ok = await self.load_one(plugin_id)
        if ok:
            await self._event_bus.publish(PluginEnabledEvent(plugin_id=plugin_id))
        return ok

    # ---- Install / uninstall / update (local, already-trusted source) -----
    async def install(self, source_dir: Path) -> str:
        """*source_dir* is an already-trusted, on-disk plugin directory
        (Phase 7's job to get it into that state) -- copied into this
        registry's own ``plugins_dir``, then loaded."""
        try:
            manifest = load_manifest(source_dir / "manifest.json")
        except PluginManifestError as err:
            raise PluginRegistryError(f"Cannot install from {source_dir}: {err}") from err

        target_dir = self._loader.plugins_dir / manifest.plugin_id
        if target_dir.exists():
            raise PluginRegistryError(f"Plugin {manifest.plugin_id!r} is already installed.")

        shutil.copytree(source_dir, target_dir)
        discovered = DiscoveredPlugin(
            plugin_id=manifest.plugin_id, plugin_dir=target_dir, manifest=manifest
        )
        self._entries[manifest.plugin_id] = _Entry(
            plugin_id=manifest.plugin_id, manifest=manifest, discovered=discovered
        )
        await self._event_bus.publish(PluginInstalledEvent(plugin_id=manifest.plugin_id))
        await self.load_one(manifest.plugin_id)
        return manifest.plugin_id

    async def uninstall(self, plugin_id: str) -> bool:
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False
        if entry.state is PluginState.RUNNING:
            await self.disable(plugin_id)
        shutil.rmtree(entry.discovered.plugin_dir, ignore_errors=True)
        del self._entries[plugin_id]
        await self._event_bus.publish(PluginUninstalledEvent(plugin_id=plugin_id))
        return True

    async def update(self, plugin_id: str, new_source_dir: Path) -> bool:
        """Real rollback support: the previous on-disk version is
        backed up before the new one is staged in; if the new version
        fails to load, the backup is restored and reloaded
        automatically -- "a failed plugin update reverts to the
        last-known good version without operator intervention"
        (Plugin Safe Core Architecture)."""
        entry = self._entries.get(plugin_id)
        if entry is None:
            raise PluginRegistryError(f"Plugin {plugin_id!r} is not installed.")
        new_manifest = self._load_update_manifest(plugin_id, new_source_dir)

        old_dir = entry.discovered.plugin_dir
        backup_dir = old_dir.with_name(f".{plugin_id}.backup")
        was_running = entry.state is PluginState.RUNNING
        from_version = entry.manifest.version
        if was_running:
            await self.disable(plugin_id)

        shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.move(str(old_dir), str(backup_dir))
        try:
            shutil.copytree(new_source_dir, old_dir)
            self._register_discovered(plugin_id, old_dir, new_manifest)
            if not await self.load_one(plugin_id):
                raise PluginRegistryError("New version failed to load.")
        except Exception as err:
            await self._rollback_update(plugin_id, old_dir, backup_dir, entry.manifest, was_running)
            _logger.warning("Plugin {!r} update failed, rolled back: {}", plugin_id, err)
            return False

        shutil.rmtree(backup_dir, ignore_errors=True)
        await self._event_bus.publish(
            PluginUpdatedEvent(
                plugin_id=plugin_id, from_version=from_version, to_version=new_manifest.version
            )
        )
        return True

    def _load_update_manifest(self, plugin_id: str, new_source_dir: Path) -> PluginManifest:
        try:
            new_manifest = load_manifest(new_source_dir / "manifest.json")
        except PluginManifestError as err:
            raise PluginRegistryError(f"Cannot update {plugin_id!r}: {err}") from err
        if new_manifest.plugin_id != plugin_id:
            raise PluginRegistryError(
                f"Update manifest name {new_manifest.plugin_id!r} does not match {plugin_id!r}."
            )
        return new_manifest

    def _register_discovered(
        self, plugin_id: str, plugin_dir: Path, manifest: PluginManifest
    ) -> None:
        discovered = DiscoveredPlugin(plugin_id=plugin_id, plugin_dir=plugin_dir, manifest=manifest)
        self._entries[plugin_id] = _Entry(
            plugin_id=plugin_id, manifest=manifest, discovered=discovered
        )
        self._permission_model.declare(plugin_id, manifest.permissions)

    async def _rollback_update(
        self,
        plugin_id: str,
        old_dir: Path,
        backup_dir: Path,
        previous_manifest: PluginManifest,
        was_running: bool,
    ) -> None:
        shutil.rmtree(old_dir, ignore_errors=True)
        shutil.move(str(backup_dir), str(old_dir))
        self._register_discovered(plugin_id, old_dir, previous_manifest)
        if was_running:
            await self.load_one(plugin_id)

    # ---- Health / status ----------------------------------------------------
    def health(self, plugin_id: str) -> HealthStatus:
        entry = self._entries.get(plugin_id)
        if entry is None:
            return HealthStatus(healthy=False, detail="Unknown plugin.")
        if entry.state is PluginState.RUNNING:
            return HealthStatus(healthy=True)
        return HealthStatus(healthy=False, detail=entry.error or f"State: {entry.state.value}")

    def status(self, plugin_id: str) -> ServiceStatus:
        entry = self._entries.get(plugin_id)
        if entry is None:
            return ServiceStatus(name=plugin_id, state="unknown")
        return ServiceStatus(
            name=plugin_id,
            state=entry.state.value,
            detail={"version": entry.manifest.version, "error": entry.error},
        )

    # ---- Introspection ------------------------------------------------------
    def get_context(self, plugin_id: str) -> PluginContext | None:
        entry = self._entries.get(plugin_id)
        return None if entry is None else entry.context

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        entry = self._entries.get(plugin_id)
        return None if entry is None else entry.manifest

    def list_manifests(self) -> tuple[PluginManifest, ...]:
        """Every currently-registered plugin's manifest -- Milestone 10A's
        Command Search reads this fresh at query time (see
        ``services/search_sources.py``'s ``CommandSearchSource``) so a
        plugin installed/enabled after the search index was first wired
        still shows up, unlike a value baked in once at DI-construction
        time would."""
        return tuple(entry.manifest for entry in self._entries.values())

    def is_registered(self, plugin_id: str) -> bool:
        return plugin_id in self._entries

    @property
    def registered_ids(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def snapshot(self) -> tuple[PluginSnapshot, ...]:
        return tuple(
            PluginSnapshot(
                plugin_id=entry.plugin_id,
                display_name=entry.manifest.display_name,
                version=entry.manifest.version,
                state=entry.state.value,
                error=entry.error,
                permissions=tuple(entry.manifest.permissions),
            )
            for entry in self._entries.values()
        )

    # ---- Internal ------------------------------------------------------
    async def _mark_failed(self, plugin_id: str, reason: str) -> None:
        entry = self._entries.get(plugin_id)
        if entry is not None:
            entry.state = PluginState.FAILED
            entry.error = reason
        _logger.warning("Plugin {!r} failed: {}", plugin_id, reason)
        await self._event_bus.publish(PluginLoadFailedEvent(plugin_id=plugin_id, detail=reason))
