"""Extension API -- Milestone 9 Task Group D, Phase 4.

:class:`PluginContext` is the *only* channel a loaded plugin has to the
rest of JARVIS -- handed to :meth:`~jarvis.core.plugins.sdk.IPlugin.
on_load` once, per the SDK contract. Every surface on it is either
permission-gated (checked against :class:`~jarvis.core.plugins.sdk.
IPermissionChecker`, Phase 5's real implementation) or scoped to just
this one plugin's own declared surface (its own commands, its own data
directory, its own settings) -- a plugin never receives a live
reference to the DI container, the database, or another plugin's data.

**UI extension points, scoped honestly.** The frontend registries this
platform's manifest fields (``commands``, ``voice_commands``,
``automation_support``) ultimately feed --
``ApplicationRegistry``/``ContributionRegistry`` and its named
instances -- live in the separate React/TypeScript process (M8) with
no in-process bridge to this Python backend. This module cannot make a
live call into them any more than any other backend code can. What it
*can* honestly do -- and does -- is expose the plugin's own manifest-
declared UI surface (:attr:`PluginContext.manifest`) in a structured,
queryable form a future FastAPI route can serve to that frontend,
exactly the same "declare it in the manifest, the frontend renders it"
pattern first-party modules already use.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import Event, PluginCustomEvent, PluginNotificationEvent
from jarvis.core.plugins.manifest import PluginManifest
from jarvis.core.plugins.sdk import IPermissionChecker, PluginConfigSchema, PluginError

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.platform import IPlatformAdapter

CommandHandler = Callable[..., Awaitable[Any]]


class PluginPermissionError(PluginError):
    """Raised by a gated surface when the calling plugin does not
    currently hold the required permission scope."""


class PluginCommandError(PluginError):
    """Raised when a plugin tries to register/invoke a command id it
    did not declare in its own manifest."""


class PluginFilesystemError(PluginError):
    """Raised for a path that would escape the plugin's own confined
    data directory, or a genuine I/O failure."""


class PluginHotkeyError(PluginError):
    """Raised when no real hotkey service is available in this
    runtime, or a hotkey operation on it fails."""


# ---------------------------------------------------------------------------
# Sub-surfaces -- one small, focused class per concern, composed onto
# PluginContext below. Mirrors this codebase's existing "thin adapter,
# not a god object" preference (see service_manager.py's own adapters).
# ---------------------------------------------------------------------------
class PluginPermissions:
    def __init__(self, plugin_id: str, checker: IPermissionChecker) -> None:
        self._plugin_id = plugin_id
        self._checker = checker

    def has(self, scope: str) -> bool:
        return self._checker.is_granted(self._plugin_id, scope)

    def require(self, scope: str) -> None:
        if not self.has(scope):
            raise PluginPermissionError(
                f"Plugin {self._plugin_id!r} does not hold permission scope {scope!r}."
            )


class PluginEventChannel:
    """Event bus access, unrestricted by permission scope (observing
    and emitting a plugin's *own* namespaced events is not one of the
    fixed permission scopes -- it is base platform capability every
    plugin gets, the same way every first-party module can already
    publish/subscribe on the shared :class:`EventBus`)."""

    def __init__(self, plugin_id: str, event_bus: EventBus) -> None:
        self._plugin_id = plugin_id
        self._event_bus = event_bus

    async def publish(self, name: str, payload: dict[str, Any] | None = None) -> None:
        """Publishes a namespaced :class:`PluginCustomEvent` -- never a
        raw core ``Event`` subclass a plugin could otherwise use to
        impersonate a first-party component."""
        await self._event_bus.publish(
            PluginCustomEvent(plugin_id=self._plugin_id, name=name, payload=payload or {})
        )

    def subscribe(
        self, event_type: type[Event], handler: Callable[[Event], Awaitable[None]]
    ) -> Any:
        """Delegates straight to the real ``EventBus`` -- returns
        whatever subscription handle it returns, so unsubscribing uses
        the exact same mechanism every other subscriber already does."""
        return self._event_bus.subscribe(event_type, handler)


class PluginCommands:
    """A plugin may only register a command id it declared in its own
    manifest's ``commands`` list -- least privilege without needing a
    dedicated permission scope for it."""

    def __init__(self, plugin_id: str, declared_ids: frozenset[str]) -> None:
        self._plugin_id = plugin_id
        self._declared_ids = declared_ids
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command_id: str, handler: CommandHandler) -> None:
        if command_id not in self._declared_ids:
            raise PluginCommandError(
                f"Plugin {self._plugin_id!r} did not declare command {command_id!r} "
                "in its manifest."
            )
        self._handlers[command_id] = handler

    async def invoke(self, command_id: str, **kwargs: Any) -> Any:
        handler = self._handlers.get(command_id)
        if handler is None:
            raise PluginCommandError(
                f"Plugin {self._plugin_id!r} has no handler registered for {command_id!r}."
            )
        return await handler(**kwargs)

    @property
    def registered_ids(self) -> frozenset[str]:
        return frozenset(self._handlers)


class PluginFilesystem:
    """Real, permission-gated (``filesystem``) file access -- confined
    to this one plugin's own data directory. Every path is resolved
    and checked against that confinement before any I/O -- a
    ``../../secrets.env``-style relative path never escapes it."""

    def __init__(self, plugin_id: str, permissions: PluginPermissions, data_dir: Path) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._data_dir = data_dir

    def _resolve(self, relative_path: str) -> Path:
        self._permissions.require("filesystem")
        candidate = (self._data_dir / relative_path).resolve()
        confined_root = self._data_dir.resolve()
        if confined_root != candidate and confined_root not in candidate.parents:
            raise PluginFilesystemError(
                f"Path {relative_path!r} escapes plugin {self._plugin_id!r}'s own data directory."
            )
        return candidate

    def read_text(self, relative_path: str) -> str:
        path = self._resolve(relative_path)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as err:
            raise PluginFilesystemError(f"Could not read {relative_path!r}: {err}") from err

    def write_text(self, relative_path: str, content: str) -> None:
        path = self._resolve(relative_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as err:
            raise PluginFilesystemError(f"Could not write {relative_path!r}: {err}") from err

    def list_dir(self, relative_path: str = ".") -> tuple[str, ...]:
        path = self._resolve(relative_path)
        if not path.is_dir():
            return ()
        return tuple(sorted(p.name for p in path.iterdir()))


class PluginNetworkAccess:
    """Real, permission-gated (``network``) *declaration* check. This
    platform does not mediate a plugin's actual outbound HTTP calls in
    this v1 -- a plugin granted ``network`` makes its own calls
    in-process, same as any other Python code. A real interception/
    quota layer is documented future work (Registry, Phase 6's Future
    Work note), not silently implied by this class's name."""

    def __init__(self, permissions: PluginPermissions) -> None:
        self._permissions = permissions

    @property
    def is_allowed(self) -> bool:
        return self._permissions.has("network")


class PluginHotkeys:
    """Real, permission-gated (``hotkey``) global hotkey registration --
    delegates to the app's own real ``HotkeyService`` (``services/
    hotkey_service.py``), the same one first-party shortcuts (toggle-
    window, push-to-talk) already register through. Every semantic id
    is namespaced under this plugin's own id
    (``plugin.<plugin_id>.<semantic>``) before reaching the shared
    service, so two plugins -- or a plugin and a first-party shortcut
    -- can never collide on a bare semantic name.

    ``hotkey_service`` is ``None`` in any runtime that hasn't wired one
    in (most unit tests, a future headless mode) -- :meth:`register`
    raises :class:`PluginHotkeyError` rather than an ``AttributeError``
    in that case, the same "clear, typed error" contract every other
    gated surface in this module already follows."""

    def __init__(
        self, plugin_id: str, permissions: PluginPermissions, hotkey_service: Any | None
    ) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._hotkey_service = hotkey_service
        self._registered: set[str] = set()

    def register(self, semantic: str, combo: str, callback: Callable[[], Any]) -> None:
        self._permissions.require("hotkey")
        if self._hotkey_service is None:
            raise PluginHotkeyError("No hotkey service is available in this runtime.")
        namespaced = f"plugin.{self._plugin_id}.{semantic}"
        self._hotkey_service.register(namespaced, combo, callback)
        self._registered.add(namespaced)

    def unregister(self, semantic: str) -> None:
        if self._hotkey_service is None:
            raise PluginHotkeyError("No hotkey service is available in this runtime.")
        namespaced = f"plugin.{self._plugin_id}.{semantic}"
        self._hotkey_service.unregister(namespaced)
        self._registered.discard(namespaced)

    def unregister_all(self) -> None:
        """Called by the Registry (Phase 6) on disable/uninstall so a
        removed plugin never leaves an orphaned global hotkey bound --
        the same "no orphan files or registered hooks" guarantee
        Marketplace uninstall already promises for other resources."""
        if self._hotkey_service is None:
            return
        for namespaced in list(self._registered):
            self._hotkey_service.unregister(namespaced)
        self._registered.clear()

    @property
    def registered_semantics(self) -> frozenset[str]:
        return frozenset(self._registered)


class PluginNotifications:
    def __init__(self, plugin_id: str, permissions: PluginPermissions, event_bus: EventBus) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._event_bus = event_bus

    async def publish(self, title: str, message: str) -> None:
        self._permissions.require("notifications")
        await self._event_bus.publish(
            PluginNotificationEvent(plugin_id=self._plugin_id, title=title, message=message)
        )


class PluginPlatformInfo:
    """Read-only capability detection -- Universal Compatibility
    (Task Group D): a plugin queries what's available instead of
    calling a raw OS API itself."""

    def __init__(self, adapter: IPlatformAdapter) -> None:
        self._adapter = adapter

    @property
    def os_family(self) -> str:
        return self._adapter.info().family.value

    @property
    def architecture(self) -> str:
        return self._adapter.info().architecture

    def has_capability(self, capability: str) -> bool:
        return self._adapter.has_capability(capability)


class PluginConfigAccess:
    """A plugin's own settings, validated against its manifest's
    ``settings_schema`` (``docs/ARCHITECTURE.md`` section 11) --
    values are always the full, defaulted set (:meth:`PluginConfigSchema.
    validate`), never a partial or raw dict."""

    def __init__(self, schema: PluginConfigSchema, initial_values: dict[str, Any]) -> None:
        self._schema = schema
        self._values = schema.validate(initial_values)

    def get_all(self) -> dict[str, Any]:
        return dict(self._values)

    def get(self, key: str) -> Any:
        return self._values.get(key)

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        merged = {**self._values, **values}
        self._values = self._schema.validate(merged)
        return self.get_all()


# ---------------------------------------------------------------------------
# The context itself.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PluginContext:
    plugin_id: str
    manifest: PluginManifest
    permissions: PluginPermissions
    events: PluginEventChannel
    commands: PluginCommands
    filesystem: PluginFilesystem
    network: PluginNetworkAccess
    hotkeys: PluginHotkeys
    notifications: PluginNotifications
    platform: PluginPlatformInfo
    config: PluginConfigAccess


def build_plugin_context(
    manifest: PluginManifest,
    *,
    event_bus: EventBus,
    permission_checker: IPermissionChecker,
    platform_adapter: IPlatformAdapter,
    data_dir: Path,
    initial_config_values: dict[str, Any] | None = None,
    hotkey_service: Any | None = None,
) -> PluginContext:
    """The one real constructor every caller (Registry, tests) uses --
    keeps ``PluginContext`` itself a plain, easily-asserted-against
    dataclass while centralizing how its sub-surfaces get wired.
    *hotkey_service* is optional -- most tests, and any runtime that
    hasn't wired one in, still get a fully-formed context; only
    :meth:`PluginHotkeys.register` actually needs it, and reports its
    own clear error if it's missing."""
    plugin_id = manifest.plugin_id
    permissions = PluginPermissions(plugin_id, permission_checker)
    data_dir.mkdir(parents=True, exist_ok=True)
    return PluginContext(
        plugin_id=plugin_id,
        manifest=manifest,
        permissions=permissions,
        events=PluginEventChannel(plugin_id, event_bus),
        commands=PluginCommands(plugin_id, frozenset(c.id for c in manifest.commands)),
        filesystem=PluginFilesystem(plugin_id, permissions, data_dir),
        network=PluginNetworkAccess(permissions),
        hotkeys=PluginHotkeys(plugin_id, permissions, hotkey_service),
        notifications=PluginNotifications(plugin_id, permissions, event_bus),
        platform=PluginPlatformInfo(platform_adapter),
        config=PluginConfigAccess(manifest.config_schema(), initial_config_values or {}),
    )
