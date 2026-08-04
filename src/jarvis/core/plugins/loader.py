"""Plugin Loader -- Milestone 9 Task Group D, Phase 2.

Discovery (``<plugins_dir>/*/manifest.json``), dependency resolution
(Kahn's-algorithm topological sort -- the same technique
``core/lifecycle/service_manager.py``'s ``_ordered_names`` already
uses), version/platform compatibility checks, and dynamic
import/unload/hot-reload of a plugin's own code.

**Deliberately more fault-tolerant than ``ServiceManager`` on cycles.**
``ServiceManager.start_all()`` raises on a circular dependency because
its service set is a small, curated, first-party list -- a cycle there
is a real programming bug that should fail loudly. A plugin set is a
third-party surface (``docs/MASTER_ROADMAP.md``'s Plugin Safe Core
Architecture: one plugin's problem must never block another's), so a
cyclic or missing dependency here isolates just the affected plugin(s)
-- reported, not raised -- while every independently-resolvable plugin
still gets an order.

**Import, not instantiation-and-lifecycle.** This module only gets a
plugin's ``IPlugin`` instance safely constructed and imported (or
un-imports it again). Actually *running* ``on_load``/``on_start``/
``on_stop`` is the Sandbox's job (Phase 3) -- keeping "can I safely get
a Python object for this plugin" and "can I safely run that object's
code" as two separate, independently-testable concerns.

Universal Compatibility (requirement 6): platform-specific
implementations share this one loader -- a manifest's ``entry_point``
can be one cross-platform string or a ``{os: "module:Class"}`` mapping,
resolved through ``core.interfaces.platform.IPlatformAdapter`` rather
than this module (or a plugin) ever branching on ``sys.platform``
directly.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger
from jarvis.core.plugins.manifest import PluginManifest, PluginManifestError, load_manifest
from jarvis.core.plugins.sdk import (
    SDK_VERSION,
    IPlugin,
    PluginError,
    parse_semver,
    version_in_range,
)

if TYPE_CHECKING:
    from jarvis.core.interfaces.platform import IPlatformAdapter

_logger = get_logger("jarvis.core.plugins.loader")

MANIFEST_FILENAME = "manifest.json"


class PluginLoadError(PluginError):
    """Raised for a specific plugin's own import/compatibility failure.
    Never raised for a problem with a *different* plugin -- see the
    module docstring's fault-isolation note."""


@dataclass(frozen=True, slots=True)
class DiscoveredPlugin:
    plugin_id: str
    plugin_dir: Path
    manifest: PluginManifest


@dataclass(frozen=True, slots=True)
class LoadOrderResult:
    """The outcome of :meth:`PluginLoader.resolve_load_order` -- both
    the resolvable order *and* what couldn't be resolved, so a caller
    can act on the former without losing visibility into the latter."""

    order: tuple[str, ...]
    unresolved: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class _LoadedEntry:
    plugin_id: str
    manifest: PluginManifest
    plugin_dir: Path
    module_name: str
    instance: Any


class PluginLoader:
    def __init__(
        self,
        plugins_dir: Path,
        *,
        platform_adapter: IPlatformAdapter,
        app_version: str,
        sdk_version: str = SDK_VERSION,
    ) -> None:
        self._plugins_dir = plugins_dir
        self._platform_adapter = platform_adapter
        self._app_version = app_version
        self._sdk_version = sdk_version
        self._loaded: dict[str, _LoadedEntry] = {}

    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir

    # ---- Discovery ------------------------------------------------------
    def discover(self) -> tuple[DiscoveredPlugin, ...]:
        """Scans ``<plugins_dir>/*/manifest.json``. A single plugin's
        unreadable/invalid manifest is logged and skipped -- never
        stops discovery of the others. Missing ``plugins_dir`` yields
        an empty result, not an error (a fresh install has none yet)."""
        if not self._plugins_dir.is_dir():
            return ()
        discovered: list[DiscoveredPlugin] = []
        for plugin_dir in sorted(p for p in self._plugins_dir.iterdir() if p.is_dir()):
            manifest_path = plugin_dir / MANIFEST_FILENAME
            if not manifest_path.exists():
                continue
            try:
                manifest = load_manifest(manifest_path)
            except PluginManifestError as err:
                _logger.warning("Skipping plugin at {}: {}", plugin_dir, err)
                continue
            if manifest.name != plugin_dir.name:
                _logger.warning(
                    "Skipping plugin at {}: manifest name {!r} does not match "
                    "its own folder name {!r}.",
                    plugin_dir,
                    manifest.name,
                    plugin_dir.name,
                )
                continue
            discovered.append(
                DiscoveredPlugin(
                    plugin_id=manifest.plugin_id, plugin_dir=plugin_dir, manifest=manifest
                )
            )
        return tuple(discovered)

    # ---- Dependency resolution -------------------------------------------
    def resolve_load_order(self, discovered: tuple[DiscoveredPlugin, ...]) -> LoadOrderResult:
        by_id = {d.plugin_id: d for d in discovered}
        remaining = dict(by_id)
        satisfied: set[str] = set()
        ordered: list[str] = []
        unresolved: dict[str, str] = {}

        progressed = True
        while remaining and progressed:
            progressed = False
            for plugin_id in list(remaining):
                deps = remaining[plugin_id].manifest.dependencies
                missing = [d for d in deps if d not in by_id]
                if missing:
                    unresolved[plugin_id] = f"Missing dependency/dependencies: {missing}"
                    del remaining[plugin_id]
                    progressed = True
                    continue
                if all(d in satisfied for d in deps):
                    ordered.append(plugin_id)
                    satisfied.add(plugin_id)
                    del remaining[plugin_id]
                    progressed = True

        for plugin_id in remaining:
            unresolved[plugin_id] = "Circular dependency among: " + ", ".join(sorted(remaining))

        return LoadOrderResult(order=tuple(ordered), unresolved=unresolved)

    # ---- Compatibility ----------------------------------------------------
    def check_compatible(self, manifest: PluginManifest) -> tuple[bool, str]:
        """Returns ``(compatible, reason)`` -- *reason* is empty when
        compatible. Never raises; an incompatible plugin is reported,
        not treated as a crash. Delegates to one small helper per
        concern (version, platform) purely to stay under this
        project's own return-statement-count lint budget -- the
        checks themselves are the same ones described in the module
        docstring, just organized for readability."""
        reason = self._check_version_compatible(manifest) or self._check_platform_compatible(
            manifest
        )
        return (reason == "", reason)

    def _check_version_compatible(self, manifest: PluginManifest) -> str:
        try:
            if not version_in_range(self._sdk_version, manifest.sdk_range):
                return (
                    f"SDK version {self._sdk_version} does not satisfy "
                    f"sdk_range {manifest.sdk_range!r}."
                )
            if parse_semver(self._app_version) < parse_semver(manifest.min_jarvis_version):
                return (
                    f"JARVIS {self._app_version} is older than this plugin's "
                    f"min_jarvis_version {manifest.min_jarvis_version!r}."
                )
        except PluginError as err:
            return str(err)
        return ""

    def _check_platform_compatible(self, manifest: PluginManifest) -> str:
        info = self._platform_adapter.info()
        if info.family.value not in manifest.supported_os:
            return f"Platform {info.family.value!r} not in supported_os {manifest.supported_os}."
        if info.architecture not in manifest.supported_arch:
            return (
                f"Architecture {info.architecture!r} not in supported_arch "
                f"{manifest.supported_arch}."
            )
        missing_capabilities = [
            cap
            for cap in manifest.required_capabilities
            if not self._platform_adapter.has_capability(cap)
        ]
        if missing_capabilities:
            return f"Missing required capabilities: {missing_capabilities}."
        return ""

    # ---- Import / unload / reload -----------------------------------------
    def import_plugin(self, discovered: DiscoveredPlugin) -> IPlugin:
        """Resolves the right entry point for this platform, imports
        the plugin's module from its own file (never touching
        ``sys.path`` -- each plugin gets a synthetic, collision-free
        module name), and constructs its declared class with a
        zero-arg constructor (the class receives its real dependencies
        later, via :meth:`~jarvis.core.plugins.sdk.IPlugin.on_load`'s
        ``context`` argument -- never a live reference at construction
        time). Raises :class:`PluginLoadError` for any failure along
        the way, always naming this one plugin."""
        manifest = discovered.manifest
        compatible, reason = self.check_compatible(manifest)
        if not compatible:
            raise PluginLoadError(f"Plugin {manifest.plugin_id!r} is not compatible: {reason}")

        entry_point = self._platform_adapter.resolve_entry_point(manifest.entry_point)
        if entry_point is None:
            raise PluginLoadError(
                f"Plugin {manifest.plugin_id!r} has no entry_point for this platform."
            )
        module_part, _, class_name = entry_point.partition(":")
        if not module_part or not class_name:
            raise PluginLoadError(
                f"Plugin {manifest.plugin_id!r} entry_point {entry_point!r} must be "
                "'module:ClassName'."
            )

        module_file = discovered.plugin_dir.joinpath(*module_part.split(".")).with_suffix(".py")
        if not module_file.is_file():
            raise PluginLoadError(
                f"Plugin {manifest.plugin_id!r} entry_point module not found: {module_file}"
            )

        module_name = f"_jarvis_plugin__{manifest.plugin_id.replace('-', '_')}"
        module = self._exec_module(module_name, module_file)

        plugin_class = getattr(module, class_name, None)
        if plugin_class is None:
            raise PluginLoadError(
                f"Plugin {manifest.plugin_id!r} entry_point class {class_name!r} not "
                f"found in {module_file}."
            )
        try:
            instance = plugin_class()
        except Exception as err:
            raise PluginLoadError(
                f"Plugin {manifest.plugin_id!r} entry_point class {class_name!r} raised "
                f"while constructing: {err}"
            ) from err
        if not isinstance(instance, IPlugin):
            raise PluginLoadError(
                f"Plugin {manifest.plugin_id!r} entry_point class {class_name!r} does not "
                "implement IPlugin (on_load/on_start/on_stop)."
            )

        self._loaded[manifest.plugin_id] = _LoadedEntry(
            plugin_id=manifest.plugin_id,
            manifest=manifest,
            plugin_dir=discovered.plugin_dir,
            module_name=module_name,
            instance=instance,
        )
        return instance

    def is_loaded(self, plugin_id: str) -> bool:
        return plugin_id in self._loaded

    def get_instance(self, plugin_id: str) -> IPlugin | None:
        entry = self._loaded.get(plugin_id)
        return None if entry is None else entry.instance

    def unload(self, plugin_id: str) -> None:
        """Drops this loader's own bookkeeping and unimports the
        module. Does not call ``on_stop`` -- that is the Sandbox/
        Registry's responsibility, run *before* this, over the still-
        live instance this method is about to discard."""
        entry = self._loaded.pop(plugin_id, None)
        if entry is not None:
            sys.modules.pop(entry.module_name, None)

    def reload(self, plugin_id: str) -> IPlugin:
        """Hot reload, where feasible: re-executes the plugin's own
        module file fresh (every :meth:`import_plugin`/:meth:`reload`
        call is a fresh ``exec_module``, not a cached import) and
        reconstructs the instance. Feasible for in-process plugins;
        an out-of-process sandboxed plugin (Phase 3) reloads by
        restarting its child process instead -- a different, also real
        mechanism, owned there, not here."""
        entry = self._loaded.get(plugin_id)
        if entry is None:
            raise PluginLoadError(f"Plugin {plugin_id!r} is not currently loaded.")
        discovered = DiscoveredPlugin(
            plugin_id=entry.plugin_id, plugin_dir=entry.plugin_dir, manifest=entry.manifest
        )
        return self.import_plugin(discovered)

    @staticmethod
    def _exec_module(module_name: str, module_file: Path) -> Any:
        """Reads *module_file*'s source and compiles+execs it directly
        -- deliberately bypassing ``SourceFileLoader``'s own ``.pyc``
        cache (which ``importlib.util.spec_from_file_location`` would
        otherwise use). That cache validates on mtime+size; two plugin
        source revisions of identical length rewritten within the same
        filesystem mtime tick are indistinguishable to it, so a real
        hot :meth:`reload` could silently keep serving stale bytecode
        -- wrong for the one thing this method exists to guarantee.
        Reading fresh every call trades a small amount of raw import
        speed (plugins are not imported on a hot path) for genuine
        reload correctness."""
        try:
            source = module_file.read_text(encoding="utf-8")
        except OSError as err:
            raise PluginLoadError(f"Could not read {module_file}: {err}") from err

        spec = importlib.util.spec_from_loader(module_name, loader=None, origin=str(module_file))
        if spec is None:
            raise PluginLoadError(f"Could not build an import spec for {module_file}.")
        module = importlib.util.module_from_spec(spec)
        module.__file__ = str(module_file)
        sys.modules[module_name] = module
        try:
            code = compile(source, str(module_file), "exec")
            # This module's entire purpose is to execute plugin code; every
            # safety boundary lives in the Sandbox (Phase 3) and Permission
            # Model (Phase 5), not here.
            exec(code, module.__dict__)
        except Exception as err:
            sys.modules.pop(module_name, None)
            raise PluginLoadError(f"Importing {module_file} raised: {err}") from err
        return module
